# G2 Execution Fact Hygiene Contract

## Purpose

This document defines certification replay execution rules for Worker execution journals.

The Worker journal is an immutable execution-fact ledger. It must record facts returned by executed actions, not expected outcomes, planned actions, or model assumptions.

## External Action Ordering Rule

For any execution-fact event:

1. Execute the external action.
2. Capture the actual returned outcome.
3. Construct the journal event from the returned outcome.
4. Persist the event.
5. Flush and validate persistence before continuing.

The following ordering is prohibited:

```
intent
  -> predicted outcome
  -> journal write
  -> external action
```

## page_opened Requirements

A `page_opened` event may only be created after the page open operation has returned.

Examples:

Allowed:

```
web.open(url)
  -> success/failure returned
  -> page_opened event
  -> durable journal append
```

Forbidden:

```
expected page availability
  -> page_opened(success=true)
  -> web.open(url)
```

## Failure Handling

If an execution fact has already been persisted incorrectly:

- do not rewrite the historical event;
- do not append a correction that hides the original fact;
- fail the current certification attempt if the immutable evidence chain is no longer trustworthy.

A new certification attempt must start from a clean execution identity.

## Scope

This contract applies to certification replay execution hygiene and does not modify the Worker route, Signal, Candidate, or Freeze contracts.
