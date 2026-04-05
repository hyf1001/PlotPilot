"""Macro Refactor API endpoints."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from application.services.macro_refactor_scanner import MacroRefactorScanner
from application.services.macro_refactor_proposal_service import MacroRefactorProposalService
from application.services.mutation_applier import MutationApplier
from application.dtos.macro_refactor_dto import (
    LogicBreakpoint,
    RefactorProposalRequest,
    RefactorProposal,
    ApplyMutationRequest,
    ApplyMutationResponse
)
from interfaces.api.dependencies import get_macro_refactor_scanner, get_macro_refactor_proposal_service, get_mutation_applier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["macro-refactor"])


@router.get("/{novel_id}/macro-refactor/breakpoints", response_model=List[LogicBreakpoint])
async def scan_breakpoints(
    novel_id: str,
    trait: str = Query(..., description="Target character trait (e.g., '冷酷')"),
    conflict_tags: Optional[str] = Query(None, description="Custom conflict tags (comma-separated)"),
    scanner: MacroRefactorScanner = Depends(get_macro_refactor_scanner)
) -> List[LogicBreakpoint]:
    """
    Scan for logic breakpoints where events conflict with character traits.

    This endpoint analyzes all narrative events in a novel to identify points
    where event tags conflict with a specified character trait.

    Args:
        novel_id: The novel ID
        trait: Target character trait to check for conflicts (e.g., "冷酷", "理性")
        conflict_tags: Optional comma-separated list of custom conflict tags
        scanner: Injected macro refactor scanner service

    Returns:
        List of logic breakpoints with conflict details

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        # Parse conflict_tags if provided
        parsed_conflict_tags = None
        if conflict_tags:
            parsed_conflict_tags = [tag.strip() for tag in conflict_tags.split(",") if tag.strip()]

        # Scan for breakpoints
        breakpoints = scanner.scan_breakpoints(
            novel_id=novel_id,
            trait=trait,
            conflict_tags=parsed_conflict_tags
        )

        logger.info(f"Scanned novel {novel_id} for trait '{trait}', found {len(breakpoints)} breakpoints")
        return breakpoints

    except Exception as e:
        logger.error(f"Error scanning breakpoints: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{novel_id}/macro-refactor/proposals", response_model=RefactorProposal)
async def generate_proposal(
    novel_id: str,
    request: RefactorProposalRequest = Body(...),
    proposal_service: MacroRefactorProposalService = Depends(get_macro_refactor_proposal_service)
) -> RefactorProposal:
    """
    Generate refactor proposal using LLM.

    This endpoint analyzes a narrative event and generates structured suggestions
    for fixing character trait conflicts or narrative inconsistencies.

    Args:
        novel_id: The novel ID
        request: Refactor proposal request with event details and author intent
        proposal_service: Injected macro refactor proposal service

    Returns:
        RefactorProposal with natural language suggestions and structured mutations

    Raises:
        HTTPException: 500 if internal error occurs
    """
    try:
        # Generate proposal using LLM
        proposal = await proposal_service.generate_proposal(request)

        logger.info(
            f"Generated proposal for novel {novel_id}, event {request.event_id}: "
            f"{len(proposal.suggested_mutations)} mutations"
        )
        return proposal

    except Exception as e:
        logger.error(f"Error generating proposal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{novel_id}/macro-refactor/apply", response_model=ApplyMutationResponse)
async def apply_mutations(
    novel_id: str,
    request: ApplyMutationRequest = Body(...),
    mutation_applier: MutationApplier = Depends(get_mutation_applier)
) -> ApplyMutationResponse:
    """
    Apply mutations to a narrative event.

    This endpoint applies a list of mutations (add_tag, remove_tag, replace_summary)
    to a specific narrative event, updating it atomically.

    Args:
        novel_id: The novel ID
        request: Apply mutation request with event_id, mutations, and optional reason
        mutation_applier: Injected mutation applier service

    Returns:
        ApplyMutationResponse with success status, updated event, and applied mutations

    Raises:
        HTTPException: 400 if event not found, 500 if internal error occurs
    """
    try:
        # Apply mutations
        result = mutation_applier.apply_mutations(
            novel_id=novel_id,
            event_id=request.event_id,
            mutations=request.mutations,
            reason=request.reason
        )

        logger.info(
            f"Applied {len(result['applied_mutations'])} mutations to event {request.event_id} "
            f"in novel {novel_id}"
        )

        return ApplyMutationResponse(
            success=result["success"],
            updated_event=result["updated_event"],
            applied_mutations=result["applied_mutations"]
        )

    except ValueError as e:
        logger.warning(f"Event not found: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error applying mutations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

