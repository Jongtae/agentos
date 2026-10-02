---
name: shopping-cart
description: A careful method for changing an online shopping cart in the owner's signed-in browser - match the exact product, variant, pack size and quantity, change only what was asked, then read the cart back before reporting. Use with a site skill for the shop when one is installed.
license: AGPL-3.0-only
---
# Changing a shopping cart

This method works on any shop through the browser tools (`browser_open`, `browser_find`, `browser_click`, `browser_type`, `browser_read`, `browser_sign_in`). A site skill can add where things are on a particular shop. Everything it says is a hint that you check on the page. Nothing here lets you pay. Never start checkout or payment. Paying is the owner's own step, and AgentOS asks for the owner's approval on every payment action.

## 1. Bind the request

Keep the owner's request whole: the shop they named, the products, the quantities and any constraints (brand, size, organic, budget, delivery type). Do not switch shop, account or delivery type on your own.

Decide what the quantity means before touching anything. Read `references/quantity.md` when the request is not obvious.

## 2. Read the current state first

1. Open the shop's cart. If the result is `login_required`, call `browser_sign_in` for that shop and end your turn telling the owner. Do not hunt for a sign-in page.
2. Note what is already in the cart: product, option and quantity. This is the baseline that you must not disturb.
3. If the request is already satisfied (for example, "ensure there is milk" and there is), change nothing and say so.

## 3. Find the exact product

Search on the shop, then match before you act. See `references/matching.md`.

- Same product, same variant (flavor, fat, organic), same pack size and unit (1L versus 900ml×2), from the shop the owner named.
- Check that it is in stock, and note the price shown.
- If several items fit equally, or none fits exactly, do not pick a substitute silently. Name the closest options with their pack size and price, and ask once.

## 4. Change only what was asked, one step at a time

- Use `browser_find` with the product's own name to reach the add or quantity control in that product's own block. Click with `effect` `mutate`. Never click a control whose nearby text names a different product.
- Reach the intended quantity with the fewest actions. If the shop has a quantity field, set it. If it only has +/- buttons, click once per unit, and read the quantity after each click before the next. Stop and re-read if a step does not change the quantity as expected.
- If a hinted label or button is missing or moved, read the page again (`browser_read` / `browser_find`) and look for it. Never click a guessed position.

## 5. Read the cart back

Open the cart again. Compare it with the baseline:

- The requested line shows the right product and option, at the quantity you intended.
- Every other line is unchanged.

Only that cart reading supports your answer. A clicked button, a pop-up or a "담았습니다" message is not proof.

## 6. When you are not sure what happened

After a timeout, an error or a restart, **read the cart before doing anything else**.

- If the change is already there, do not click again.
- If the cart changed in a way you did not cause (someone else, or another assistant sharing the account, changed it), stop. Report what you see, without claiming or repeating your change.
- If you cannot tell whether your click counted, say it is unknown and what the cart shows now.

## 7. Report

Report in one short answer:

- what is in the cart now for the requested items, with quantity and price as read from the cart;
- anything you did not do, and why (out of stock, ambiguous, signed out);
- that the owner pays in the shop's own app or website.

Do not send a cart link as proof. It opens signed out on the owner's other devices. Never put cookies, passwords or order history into a message or memory.
