import uuid
from typing import List, Dict, Any, Optional
from memory_thread.models.events import Event, EntityState, ActionEnum, ActorEnum
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TransactionManager:
    """
    Handles Multi-Entity Atomic Updates.
    Maps a single Root Event (Transfer) to multiple Entity State updates.
    """
    def __init__(self):
        self.tms = TMSService()

    def process_transaction(self, root_event: Event, context_states: Dict[uuid.UUID, EntityState]) -> Dict[uuid.UUID, EntityState]:
        """
        Interprets a Root Event and applies effects to multiple entities.
        Returns the new states for all involved entities.
        """
        updated_states = {}

        # Scenario: Supply Chain Transfer
        # Event: UPDATE Factory {transfer_to: Warehouse, qty: 200}

        if root_event.action == ActionEnum.UPDATE and "transfer_to" in root_event.delta:
            source_id = root_event.object_id
            target_id_str = root_event.delta["transfer_to"]
            target_id = uuid.UUID(target_id_str)
            qty = root_event.delta.get("qty", 0)

            # 1. Update Source (Factory)
            if source_id in context_states:
                source_state = context_states[source_id]
                # Synthesize a local event for the source
                # Or just apply logic directly?
                # To maintain Event Sourcing purity, we should ideally log derived events?
                # "Factory Shipped 200"

                # Logic: Decrement
                # We reuse StateDerivation but we need to inject the "decrement" semantic
                # which isn't in the generic UPDATE event delta (which just says 'transfer_to').

                # We synthesize a specific delta for the state application
                debit_event = root_event.copy() # Shallow copy
                debit_event.action = ActionEnum.REMOVE # Use REMOVE for decrement
                debit_event.delta = {"inventory": qty}

                new_source = StateDerivationService.apply_event(source_state, debit_event)
                updated_states[source_id] = new_source

            # 2. Update Target (Warehouse)
            if target_id in context_states:
                target_state = context_states[target_id]

                credit_event = root_event.copy()
                credit_event.object_id = target_id
                credit_event.action = ActionEnum.ADD # Increment
                credit_event.delta = {"inventory": qty}

                new_target = StateDerivationService.apply_event(target_state, credit_event)
                updated_states[target_id] = new_target

        else:
            # Default: Single entity update
            if root_event.object_id in context_states:
                s = context_states[root_event.object_id]
                updated_states[root_event.object_id] = StateDerivationService.apply_event(s, root_event)

        return updated_states
