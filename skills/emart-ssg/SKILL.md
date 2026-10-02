---
name: emart-ssg
description: Site know-how for Emart's online mall on SSG.COM (이마트몰, emart.ssg.com) - where search results and the cart are, how sign-in works and what to keep in mind there. Use together with the shopping-cart skill when the owner shops at Emart or SSG.
license: AGPL-3.0-only
---
# Emart mall on SSG.COM

Follow the `shopping-cart` skill for the method. This skill only adds what is known about this site.

**Provenance:** observed in redacted AgentOS browser records, September–October 2026. These are hints: pages change, so check each one on the page itself. If a hint does not hold, look again with `browser_read` or `browser_find`, and report the difference instead of guessing.

## Places

| What | Observed address | Page title seen |
| --- | --- | --- |
| Emart mall home | `https://emart.ssg.com/` | 원하는 상품을 원하는 시간에 쓱, 이마트몰 |
| Emart mall search results | `https://emart.ssg.com/search.ssg` (reached through the site's search box) | `<검색어> - 추천•인기 상품, 이마트몰` |
| Cart (shared by all SSG.COM malls) | `https://pay.ssg.com/cart/dmsShpp.ssg` | 장바구니, 믿고 사는 즐거움 SSG.COM |
| Category pages | under `https://emart.ssg.com/disp/` | 카테고리 > … |

## What to keep in mind

- **One account and one cart for every mall.** Emart mall is one mall inside SSG.COM. A sign-in on `ssg.com` covers it, and the cart is the SSG.COM cart. If the cart page asks for sign-in, call `browser_sign_in` with the cart address.
- **Stay in the Emart mall.** For an Emart request, search on `emart.ssg.com`. Results on `www.ssg.com` mix in other sellers and malls, whose products, prices and delivery differ.
- **Delivery types.** The mall offers more than one delivery type, such as 쓱배송 and 새벽배송. Keep the type the owner asked for, and do not switch an item's delivery type on your own. If the owner named none, leave the site's default and say which one the item uses.
- **Check the cart line is the item you chose.** The SSG.COM cart can also hold items from other malls and sellers. When reading the cart back, check that the line is the Emart item you added, using any mall, seller or delivery label the line shows, and not the same name from elsewhere.
- **Payment** is the owner's own step in the SSG.COM app or website. Do not open checkout.
