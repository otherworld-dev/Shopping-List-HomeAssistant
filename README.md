# Nextcloud Shopping List for Home Assistant

This integration brings the lists from the [Shopping List](https://github.com/otherworld-dev/Shopping-List) app for Nextcloud into Home Assistant. Each list becomes a Home Assistant to-do list, so you can put it on a dashboard, for example on a tablet in the kitchen, and add to it, tick it off and change it by voice.

Items read the same way as in the app, with the amount and then the name ("2 pints Milk"), and the shop area and who added the item underneath. Anything you add is read by the server the same way as typing it into the app, so "two pints of milk" lands as Milk, 2 pints, in Dairy, and tops up the Milk already on the list rather than adding a second one.

## What you need

- Home Assistant 2026.10 or later.
- The Shopping List app 1.13.0 or later on your Nextcloud. Setup checks this and tells you if the app needs updating.

## Installing

The integration is installed through [HACS](https://hacs.xyz/) as a custom repository:

1. In HACS, open the menu, choose **Custom repositories** and add `https://github.com/otherworld-dev/Shopping-List-HomeAssistant` with the type **Integration**.
2. Search for **Nextcloud Shopping List**, download it and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and choose **Nextcloud Shopping List**.

## Setting it up

Enter the address of your Nextcloud, for example `cloud.example.com` (https is used if you leave it out), and then choose how to sign in:

- **Sign in through Nextcloud** opens Nextcloud's own page asking you to grant Home Assistant access. Once you grant it, setup carries on by itself. Nextcloud gives Home Assistant its own app password, so your real password never reaches Home Assistant, and you can revoke it at any time under **Personal settings → Security** in Nextcloud.
- **Enter an app password** is there if the first way doesn't suit, for example when Nextcloud is behind a login page Home Assistant can't open. Create an app password under **Personal settings → Security** and enter it with your login name.

If the app password is revoked later, Home Assistant asks you to sign in again.

Every list your account can see shows up, your own and the ones shared with you. Lists you make later show up by themselves.

## Options

Open the integration's **Configure** to change:

- **Lists to hide**: ticked lists don't show up in Home Assistant. This is useful if you have a lot of lists and only want one or two in the kitchen.
- **Label for changes**: what the app shows against items Home Assistant adds or ticks, "Home Assistant" by default. The app shows it with an "app" mark next to it, so it can never pass for a person, and hovering over it shows whose account was used. Set it to something like "Kitchen" if you prefer, or leave it empty to show the account's own name.

## Using it by voice

Adding uses Home Assistant's own sentence, so it works in any language Home Assistant supports:

| You say | What happens |
|---|---|
| Add two pints of milk to weekly shop | Milk, 2 pints, in Dairy, or 2 pints more on the Milk already there |
| Check off milk on weekly shop | Milk is ticked off, whatever its amount |
| Change milk to three pints on weekly shop | Milk's amount becomes 3 pints |
| Remove milk from weekly shop | Milk is removed |

"Tick off", "mark milk as done", "set milk to three pints" and "delete milk from weekly shop" work as well, and "the" and "list" are optional ("tick off the milk on the weekly shop list"). These three are in English for now.

Checking off and removing find the item by its name without the amount, so you say "milk" rather than "2 pints milk". Home Assistant's own check-off sentence needs the item's whole text, which is why the integration adds its own.

The sentences work with Home Assistant's own voice assistant and with AI assistants (OpenAI, Google, Ollama and others). An AI assistant also gets the three actions as tools, so you can talk to it more freely, for example "I've got the milk, tick it off", and it can read the list with Home Assistant's own tools.

### Giving a list another name

You say a list's name as it is in the app. To say "shopping list" for a list called "Weekly shop", give it an alias: **Settings → Voice assistants → Expose**, choose the list and add the alias. The integration picks it up straight away.

If two of your lists have the same name, for example your own "Shopping" and one shared with you, a command naming them changes neither and says so. Give one of them an alias and take the list's own name off its voice names, in the same place.

If two Nextcloud accounts are set up and both can see a shared list, it is still one list, so checking off, changing or removing only happens once. Home Assistant's own add sentence refuses a name two of its to-do lists share, so to add to that list by voice, hide it in one of the accounts' options.

### Home Assistant's own shopping list

Home Assistant has a built-in Shopping List integration whose list is also called "Shopping list". If you have it set up, "add milk to my shopping list" may go to that one instead. Remove it under **Settings → Devices & services**, or rename it, if you only use this one.

### Language

The server reads each line in the language set for your Nextcloud account, which decides the units it knows and how it spells out amounts. If your Nextcloud is set to German and you speak English to Home Assistant, the units won't be recognised, so keep the two the same.

## What it doesn't do

Lists, shop areas, shares and photos are managed in the app. Changes made elsewhere show up within 30 seconds.

## Development

Home Assistant doesn't run on Windows, so the tests run in Docker:

```bash
docker build -t ncsl-ha-test -f tests/Dockerfile .
docker run --rm -v "$PWD:/app" -w /app ncsl-ha-test python -m pytest tests -q
```

## Licence

AGPL-3.0, the same as the Shopping List app.
