# OKEY17 / GÖBEK17 — v158 RACK +15% PREVIEW

**Parent canonical:** `gobek17-157-immutable-meld-body-guard`
**Status:** EXPERIMENTAL PREVIEW — not canonical until user approval.

Presentation-only rack trial:
- Human rack tile geometry: 68×94 -> 78×108 px (~+15%).
- Rack number face: 47 -> 54 px.
- Slot pitch: 76 -> 81 px.
- Horizontal rack body: x 244/w 1048 -> x 236/w 1064.
- Lower rack row: y 886 -> 872 so 108px tiles still terminate cleanly at the lower wooden lip.
- Board/free tiles remain 47×65; opened-meld sizing/rules unchanged.

QA:
- 768×356, 915×412, 1536×712, 1842×854: no rack tile overlap and no stage overflow.
- Worst visual distribution tested: 13 tiles on one rack row + 2 on the other.
- Engine E.check PASS.
- v152 rules PASS.
- v153 side-take rules PASS.
- v157 immutable-meld-body rules PASS.
