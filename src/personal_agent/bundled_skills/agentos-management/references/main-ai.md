# Changing the Main AI

The Main AI is the route that does the owner's work: a subscription CLI or a model API. `main_ai.route` selects it and `main_ai.model` selects the model on that route.

## Steps

1. Call `settings_read` with category `main_ai`. `route.options` lists only the routes that are connected and checked. `model.options` lists the models of the current route, when the route allows choosing one.
2. If the owner names a route or model that is not listed, say it is not available now and name what is. Connecting a new route, or entering a key, is done by the owner in Settings, never in conversation.
3. Propose exactly one change: `settings_change` with category `main_ai`, setting `route` or `model`. The draft says where later work will be sent. Repeat that destination to the owner.

## Keep these states apart

- **Requested:** a draft exists. Nothing has changed yet.
- **Configured:** the setting now names the new route or model.
- **Executable:** the route is connected and its check passed. Only such routes appear as options.
- **Actually used:** shown only by a later Work's own record of which worker ran.

Applying a route or model change can take a while, because the owning service checks the route. Never claim that check, or a test answer, succeeded unless a result says so. Do not start extra work just to try the new route.

## Running Work versus the next Work

A Work that is already running keeps the route it started with. The change applies from the next request on. Say so when the owner changes the Main AI in the middle of a task.
