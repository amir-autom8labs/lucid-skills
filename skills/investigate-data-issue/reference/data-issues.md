# Data issues: symptoms and confirming questions

What each data issue class looks like and the questions that confirm it. Per check
details (what it compares, which classes cause it, which screen fixes it) come from
`get_check_catalogue`; this page is the general picture.

## D1 Misplaced amount
- **Symptoms:** a line too high or too low; a figure that disagrees with the user's
  own workbook; a P&L note that does not add up; an account on an unexpected line.
- **Confirm:** which accounts make up the line, with their classes and the rule that
  placed each (`get_line_placement`; for a Cash Flow line, `explain` and
  `drilldown`); one account's class and where it lands (`get_account`); who changed
  the class and when (`get_account_history`).
- **Fix:** the account's page (change the class).

## D2 Unclassified or incomplete account
- **Symptoms:** money missing from a statement; Balance Sheet out of balance; empty
  P&L bands; "Unclassified" rows; "accounts need a class".
- **Confirm:** `get_open_items` shows the accounts already waiting for a class
  in the work queue; the check's breakdown names the accounts and amounts that land
  nowhere; a Cash Flow section check names each class with no section and its
  amount; `list_accounts` with a missing-required-class filter finds every account
  in the same state; `get_account` shows the missing class (`required_label_missing`);
  history shows when the account arrived (chart refresh, import).
- **Fix:** Work → Accounts (add the class).

## D3 Cash and card definition
- **Symptoms:** Balance Sheet cash differs from the Cash Flow's closing cash; the
  year's opening cash differs; an empty card line; cash warnings.
- **Confirm:** on the cash check, the Balance Sheet side lists each cash class as one
  line and names any cash account shown under another class; the items name the
  accounts behind a difference. `get_account` shows the cash setting and the Balance
  Sheet class side by side; `list_accounts` filtered by class and cash tick finds
  every unticked account in a cash class. A cash account outside a cash class, or a bank account
  left unticked, shows as a cash warning rather than a failing check: on the
  account's `disagreements` (open or acknowledged) and in `get_open_items`.
- **Fix:** Work → Cash accounts (tick or untick), or the account's page (move it to
  a cash class). Whether an account is cash is often **the user's decision**.

## D4 Routing
- **Symptoms:** subtotals that look added instead of subtracted; a whole class on an
  unexpected line; cash showing as Unclassified on the Cash Flow; a P&L total with no
  line.
- **Confirm:** `get_line_placement` shows each class on the line with its routing
  heading and sign, and the same-class accounts that land elsewhere; `get_account`
  landings show the rule for one account; the check catalogue names the routing
  causes.
- **Fix:** Settings → Statement routing.

## D5 Missing or unposted adjusting entries
- **Symptoms:** a month that breaks an account's usual pattern (depreciation,
  accruals, provisions); close readiness blocked by drafts; base and adjusted views
  differ unexpectedly.
- **Confirm:** close readiness lists drafts waiting for approval; compare the account
  across months with the report tools; the adjusted view against the base view.
- **Fix:** Work → AJEs (adjusting entries) (create, edit or approve).

## D6 Source data gaps
- **Symptoms:** a month with no activity; doubled amounts; Balance Sheet out by a
  few entries; entries held back.
- **Confirm:** the debits and credits check and its parts; held entries in status and
  close readiness.
- **Fix:** Imports (re-import or sync), or the source system.

## D7 Account identity
- **Symptoms:** supplier or customer cards asked to be classified as general ledger;
  supplier balances on general ledger lines.
- **Confirm:** `get_open_items` shows the import or classification items already
  open for the cards; `get_account` shows the ledger type and where it came from;
  `list_accounts` filtered by ledger type lists accounts by their stored type, so
  it finds a card's siblings, not the cards stored as general ledger.
- **Fix:** the ledger type is confirmed when the account first arrives at import
  (Imports), or corrected in the source system; the account's page shows it but
  does not change it.

## D8 Intercompany
- **Symptoms:** the group Balance Sheet out of balance; intercompany balances left
  after eliminations.
- **Confirm:** consolidation readiness and its breakdown per company; the group
  balance checks list each company's part.
- **Fix:** Work → Eliminations (pairing and eliminations); an amount the two
  companies record differently needs an adjusting entry (Work → AJEs) or a
  correction in the source books.

## D9 Exchange rate on an adjusting entry
- **Symptoms:** an exchange difference that is too large; a converted amount that
  disagrees with the user's own calculation.
- **Confirm:** explain the cell; the adjusting entry's lines.
- **Fix:** Work → AJEs (adjusting entries).

## D10 Period state
- **Symptoms:** a class change that does not reach a closed month; old classes still
  shown for a closed month.
- **Confirm:** the period's status; findings of classes changed after closing.
- **Fix:** Work → Periods (reopen), or a reversing entry.
