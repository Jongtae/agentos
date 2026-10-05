---
name: map-directions
description: A method for answers about going somewhere (a shop, a meeting, home) - start from where the owner is, say when to leave and how to get there (mode, approximate time, parking), and give one link that opens the route in the owner's preferred map service. Use whenever the owner will go to a place, not only when they ask for directions.
license: AGPL-3.0-only
---
# Getting the owner there

Use this when your answer sends the owner somewhere: a shop's opening time, a restaurant, a meeting place, the way home. A secretary does not stop at the place's details. They also say when to leave and how to get there.

## 1. Where the owner is starting from

Use the best evidence you have and say which one you used:

1. A fresh shared position in the current context.
2. The situation note or the recent conversation ("집에 가는 중", "회사야").
3. A saved place in the owner profile (home, work), stated as an assumption: "집에서 출발한다면".

If none of these settles it, and the answer would really change, give the answer for the likeliest place and name it, or offer the two likely places in one line. Do not guess silently, and do not stop to ask when a stated assumption works.

## 2. When to leave and how

- Work backwards from the time that matters: the opening time, the reservation or the last order. "10시에 열고 집에서 차로 10분쯤이라 9시 50분쯤 나서면 됩니다."
- Give the likely mode for this owner and distance. Walking is the default for short distances; give a car time when the owner usually drives or the place is far. Add public transport when it is a real option.
- Travel times without a route service are estimates. Say "약", base them on distance, and never present them as live traffic. The map link in step 3 shows the live time.
- Mention parking when the owner may drive: whether the place has a lot or uses a building's lot, and any fee or time limit you found. If you could not find it, say so in a few words.

## 3. One link in the owner's map service

- Use the map service the owner prefers. It is a saved preference in the owner profile. If none is saved, ask once in the same reply which one they use, and save the answer with `save_memory` as a preference.
- Build the link from that service's reference file in `references/` (read it with `skill_resource`). Prefer a route link to the destination. Use a search link only when you lack coordinates or a place id.
- Put the link right next to the travel line, not in a list at the end.
- If there is no reference file for the owner's service, give the place's address plainly and say the link format for that service is not known yet.

## Never

- Never present an estimate as checked, or a stale position as current.
- Never open or change anything for the owner. A link is text the owner chooses to open.
