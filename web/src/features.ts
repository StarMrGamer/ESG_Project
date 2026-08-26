/**
 * Feature flags — things that are BUILT and WORKING but not currently shown.
 *
 * A flag here is not a half-finished feature. It is a decision that has not settled yet, kept
 * cheap to reverse: the code, the tests and the API all stay live, so flipping the boolean is
 * the whole change and nothing has to be rebuilt or re-reviewed to bring it back.
 */

/**
 * The analyst's client book — roster + pre-meeting brief (`clients.py`, `brief.py`,
 * `ClientsTab.tsx`, `/api/clients/*`). Hidden pending a team decision on whether managing client
 * records belongs in this product at all. Everything behind it still works and is still tested;
 * set this to `true` and the tab comes back exactly as it was.
 */
export const SHOW_CLIENTS = false
