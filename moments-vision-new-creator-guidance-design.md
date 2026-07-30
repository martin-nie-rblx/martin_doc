# Moments Vision: New Creator Guidance Design

Date: 2026-07-29

## Goal

Add a mobile-portrait prototype flow to the Moments feed's plus menu. A new
menu action named **New Creator** opens a Capture library empty state and a
three-step "How to use Capture" guide based on the supplied reference images.

## Scope

- Mobile portrait only.
- Add **New Creator** as the last item in the existing plus-button menu.
- Use a Capture/camera icon for the new menu item.
- Preserve all existing menu actions and creation flows.
- Rebuild the screens in HTML and CSS rather than using full-screen
  screenshots.

## Architecture

Keep the feature isolated from the existing creation implementation:

- `js/new-creator.js` owns DOM construction, state, navigation, and cleanup.
- `css/new-creator.css` owns the mobile portrait presentation.
- The same module and stylesheet also own the post-guidance RIVALS entry sheet;
  no separate bottom-sheet abstraction is introduced for this prototype.
- `window.NewCreatorFlow.open()` provides the integration point used by the
  existing menu in `js/create.js`.
- `index.html` loads the new stylesheet and script using the repository's
  existing cache-busting convention.

Instructional artwork may be extracted from the supplied references and stored
as local image assets. Text, buttons, navigation, spacing, and interaction
surfaces remain live HTML and CSS.

## Screen and Navigation Flow

The references are ordered by their filename prefixes:

1. `1-...png`: **Your Capture library**
2. `2-...png`: Join an Experience and select the hamburger menu
3. `3-...png`: Enable the Capture controls
4. `4-...png`: Capture photos and videos of gameplay

Navigation behavior:

- Selecting **New Creator** opens screen 1.
- **How to Capture** on screen 1 advances to screen 2.
- **Continue** advances from screen 2 to 3 and from screen 3 to 4.
- **Back** on screen 3 returns to screen 2.
- **Back** on screen 4 returns to screen 3.
- **Go Capture** on screen 4 returns to the Moments feed and immediately opens
  the RIVALS game-intro sheet.
- **Back** on screen 1 returns to the Moments feed.
- The top-right close button on every screen returns to the Moments feed.
- The existing bottom navigation stays visible with Moments selected.

Ordinary close and Back paths never open the game-intro sheet. The
`go-capture` action is distinct from the shared close action so this behavior
cannot be triggered accidentally.

## RIVALS Entry Sheet

After **Go Capture**, a scrim darkens the Moments feed and a bottom sheet opens
immediately. The sheet follows the supplied reference and contains:

- the existing local RIVALS game thumbnail;
- title **RIVALS**;
- creator **Nosniy Games** with a verified badge;
- **Maturity: Mild**;
- **93%** rating;
- a full-width blue Play button.

Opening the sheet pauses the active Moment video. The Play button, Escape, and
a tap on the dark backdrop outside the sheet each dismiss the sheet and resume
playback. Taps inside the sheet do not dismiss it unless they activate Play.
The entry sheet is mobile-portrait only.

Device and orientation changes close the sheet without resuming playback,
because the user is leaving the mobile-portrait Moments view.

## Visual Design

- Match the existing 393 x 852 mobile portrait phone frame.
- Follow the dark Roblox visual treatment shown in the references.
- Recreate typography, spacing, buttons, pagination dots, and bottom
  navigation as HTML/CSS.
- Match the supplied RIVALS reference for the scrim, rounded top corners,
  drag handle, metadata rows, and Play button.
- Use the supplied references as the visual source of truth.
- Do not introduce landscape or desktop variants.

## Accessibility and State

- Use semantic buttons for every interactive control.
- Provide accessible labels for the close control and icon-only elements.
- Keep focusable controls keyboard-activatable.
- Maintain one explicit current-screen state in `new-creator.js`.
- Closing or completing the flow resets it so the next launch starts at
  screen 1.
- Track the guidance and RIVALS sheet as separate visible states.
- Return focus appropriately when either surface closes.
- Add `window.pauseMomentPlayback()` beside the existing
  `window.startMomentPlayback()` player API.
- Pause only the active Moment when the RIVALS sheet opens.
- Distinguish user dismissal, which resumes playback, from lifecycle cleanup,
  which leaves playback paused.

## Verification

- Confirm the menu shows **New Creator** last with the Capture icon.
- Confirm filename-order navigation: 1 to 2 to 3 to 4.
- Verify all Continue, Back, Go Capture, and close paths.
- Confirm Go Capture returns to the feed and immediately opens the RIVALS
  sheet.
- Confirm Back and close paths do not open the RIVALS sheet.
- Confirm opening RIVALS pauses the active Moment before the sheet appears.
- Confirm Play, Escape, and backdrop taps dismiss the RIVALS sheet and resume
  playback.
- Confirm taps inside the sheet do not dismiss it.
- Confirm device and orientation cleanup closes the sheet without resuming.
- Confirm relaunching starts at screen 1.
- Confirm existing Gallery and other plus-menu actions are unchanged.
- Confirm the flow is limited to mobile portrait.
- Visually compare each screen against its supplied reference at 393 x 852.
