# New Creator Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mobile-portrait New Creator entry to the Moments plus menu that opens a four-screen Capture library and guidance flow, then offers RIVALS as the game-entry destination after Go Capture.

**Architecture:** A focused `js/new-creator.js` module builds and controls the overlay and exposes `window.NewCreatorFlow.open()`. A focused `css/new-creator.css` stylesheet owns the presentation. The existing create menu only adds the final menu item and delegates opening to the new module.

**Tech Stack:** Plain HTML, CSS, JavaScript, Node.js built-in test runner, Python static server, macOS `sips`

---

## File Map

- Create `js/new-creator.js`: state transitions, DOM construction, open/close behavior.
- Create `css/new-creator.css`: portrait-only overlay layout and styling.
- Create `tests/new-creator.test.js`: state-machine unit tests and source integration checks.
- Create `assets/images/new-creator/library-illustration.png`: cropped empty-state artwork.
- Create `assets/images/new-creator/step-join.png`: cropped first guidance card.
- Create `assets/images/new-creator/step-enable.png`: cropped second guidance card.
- Create `assets/images/new-creator/step-capture.png`: cropped third guidance card.
- Modify `js/create.js:4203-4238`: append the New Creator menu item and delegate its click.
- Modify `index.html:66-70,4364-4366`: load the new stylesheet and script with cache versions.

No implementation commit should be created unless the user explicitly requests one.

### Task 1: Prepare the Reference Artwork

**Files:**
- Source: `/Users/mnie/.cursor/projects/Users-mnie-dev/assets/1-e5202414-1752-4bac-a57a-b23bfccb42f1.png`
- Source: `/Users/mnie/.cursor/projects/Users-mnie-dev/assets/2-c8945944-634d-4183-a7b1-a4ddc3954f12.png`
- Source: `/Users/mnie/.cursor/projects/Users-mnie-dev/assets/3-93f07142-72cb-4924-8d56-c6884028db16.png`
- Source: `/Users/mnie/.cursor/projects/Users-mnie-dev/assets/4-02772d66-9396-45c5-a98e-72b63755e4ba.png`
- Create: `assets/images/new-creator/library-illustration.png`
- Create: `assets/images/new-creator/step-join.png`
- Create: `assets/images/new-creator/step-enable.png`
- Create: `assets/images/new-creator/step-capture.png`

- [ ] **Step 1: Confirm source image dimensions**

Run:

```bash
sips -g pixelWidth -g pixelHeight \
  /Users/mnie/.cursor/projects/Users-mnie-dev/assets/{1-e5202414-1752-4bac-a57a-b23bfccb42f1,2-c8945944-634d-4183-a7b1-a4ddc3954f12,3-93f07142-72cb-4924-8d56-c6884028db16,4-02772d66-9396-45c5-a98e-72b63755e4ba}.png
```

Expected: every image reports `472 x 1024`.

- [ ] **Step 2: Create the asset directory**

Run:

```bash
mkdir -p assets/images/new-creator
```

- [ ] **Step 3: Crop the artwork**

Use copies so the supplied source images remain untouched:

```bash
sips -c 150 190 --cropOffset 345 141 \
  /Users/mnie/.cursor/projects/Users-mnie-dev/assets/1-e5202414-1752-4bac-a57a-b23bfccb42f1.png \
  --out assets/images/new-creator/library-illustration.png
sips -c 200 350 --cropOffset 382 61 \
  /Users/mnie/.cursor/projects/Users-mnie-dev/assets/2-c8945944-634d-4183-a7b1-a4ddc3954f12.png \
  --out assets/images/new-creator/step-join.png
sips -c 200 350 --cropOffset 395 61 \
  /Users/mnie/.cursor/projects/Users-mnie-dev/assets/3-93f07142-72cb-4924-8d56-c6884028db16.png \
  --out assets/images/new-creator/step-enable.png
sips -c 200 350 --cropOffset 395 61 \
  /Users/mnie/.cursor/projects/Users-mnie-dev/assets/4-02772d66-9396-45c5-a98e-72b63755e4ba.png \
  --out assets/images/new-creator/step-capture.png
```

- [ ] **Step 4: Verify derived dimensions**

Run:

```bash
sips -g pixelWidth -g pixelHeight assets/images/new-creator/*.png
```

Expected: the library illustration is `190 x 150`; each guidance card is `350 x 200`.

### Task 2: Build the Flow State Machine Test-First

**Files:**
- Create: `tests/new-creator.test.js`
- Create: `js/new-creator.js`

- [ ] **Step 1: Write failing state-transition tests**

Create `tests/new-creator.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  initialScreen,
  advanceScreen,
  backScreen,
} = require('../js/new-creator.js');

test('guidance advances in filename order', () => {
  assert.equal(initialScreen, 'library');
  assert.equal(advanceScreen('library'), 'join');
  assert.equal(advanceScreen('join'), 'enable');
  assert.equal(advanceScreen('enable'), 'capture');
});

test('guidance back navigation reverses one screen', () => {
  assert.equal(backScreen('enable'), 'join');
  assert.equal(backScreen('capture'), 'enable');
});

test('index loads New Creator CSS before New Creator JS', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  assert.match(html, /css\/new-creator\.css\?v=\d+/);
  assert.match(html, /js\/new-creator\.js\?v=\d+/);
  assert.ok(html.indexOf('css/new-creator.css') < html.indexOf('js/new-creator.js'));
});

test('all four artwork assets exist', () => {
  for (const name of [
    'library-illustration.png',
    'step-join.png',
    'step-enable.png',
    'step-capture.png',
  ]) {
    assert.ok(fs.existsSync(path.join(
      __dirname, '..', 'assets', 'images', 'new-creator', name,
    )), `${name} should exist`);
  }
});
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```bash
node --test tests/new-creator.test.js
```

Expected: FAIL because `js/new-creator.js` does not exist.

- [ ] **Step 3: Add the pure transition API**

Start `js/new-creator.js` with:

```js
(function (global) {
  'use strict';

  const initialScreen = 'library';
  const NEXT = Object.freeze({
    library: 'join',
    join: 'enable',
    enable: 'capture',
    capture: 'capture',
  });
  const BACK = Object.freeze({
    enable: 'join',
    capture: 'enable',
  });

  function advanceScreen(screen) {
    return NEXT[screen] || initialScreen;
  }

  function backScreen(screen) {
    return BACK[screen] || initialScreen;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { initialScreen, advanceScreen, backScreen };
  }

  if (!global || !global.document) return;

  // Browser implementation is added in Task 3.
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: Run the focused state tests**

Run:

```bash
node --test --test-name-pattern="guidance" tests/new-creator.test.js
```

Expected: the two guidance tests PASS; index/asset checks may still fail until Task 3.

### Task 3: Implement the Accessible Portrait Overlay

**Files:**
- Modify: `js/new-creator.js`
- Create: `css/new-creator.css`
- Modify: `index.html:66-70,4364-4366`

- [ ] **Step 1: Add screen descriptors and DOM construction**

Inside the browser branch of `js/new-creator.js`, define:

```js
  const SCREENS = Object.freeze({
    library: {
      title: 'Your Capture library',
      description: 'This is where your Captures will appear.',
      artwork: 'assets/images/new-creator/library-illustration.png',
      artworkAlt: '',
      dots: null,
      actions: [
        { action: 'advance', label: 'How to Capture', primary: true },
        { action: 'close', label: 'Back', primary: false },
      ],
    },
    join: {
      title: 'How to use Capture',
      description: 'Join an Experience with Captures enabled and select the hamburger menu',
      artwork: 'assets/images/new-creator/step-join.png',
      artworkAlt: 'Open the Roblox menu inside an Experience',
      dots: 0,
      actions: [{ action: 'advance', label: 'Continue', primary: true }],
    },
    enable: {
      title: 'How to use Capture',
      description: 'Enable the Capture controls',
      artwork: 'assets/images/new-creator/step-enable.png',
      artworkAlt: 'Select Captures from the Roblox menu',
      dots: 1,
      actions: [
        { action: 'back', label: 'Back', primary: false },
        { action: 'advance', label: 'Continue', primary: true },
      ],
    },
    capture: {
      title: 'How to use Capture',
      description: 'Capture photos and videos of gameplay',
      artwork: 'assets/images/new-creator/step-capture.png',
      artworkAlt: 'Use the Capture Video and Capture Photo controls',
      dots: 2,
      actions: [
        { action: 'back', label: 'Back', primary: false },
        { action: 'close', label: 'Done', primary: true },
      ],
    },
  });
```

Build one `.new-creator` dialog appended directly to `.phone-frame`, with:

- a top-right semantic close button;
- a content region containing the title, artwork, dots, and description;
- an action row populated from `SCREENS[currentScreen].actions`;
- `role="dialog"`, `aria-modal="true"`, and `aria-label="New Creator guidance"`;
- event delegation on `[data-new-creator-action]`;
- `open()`, `close()`, and `render()` functions;
- reset to `initialScreen` in both `open()` and `close()`;
- a guard in `open()` that returns without opening when `.phone-frame` has
  `.is-landscape` or when `#desktop-shell` is active;
- `global.NewCreatorFlow = { open, close }`.

Use this action handler:

```js
  function handleAction(action) {
    if (action === 'advance') {
      currentScreen = advanceScreen(currentScreen);
      render();
      return;
    }
    if (action === 'back') {
      currentScreen = backScreen(currentScreen);
      render();
      return;
    }
    close();
  }
```

- [ ] **Step 2: Add portrait styling**

Create `css/new-creator.css` with these core constraints:

```css
.new-creator {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 90px;
  left: 0;
  z-index: 160;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #121215;
  color: #f7f7f8;
  font-family: var(--font-family-base);
  opacity: 0;
  visibility: hidden;
  transform: translateX(100%);
  transition: opacity 180ms ease, transform 280ms cubic-bezier(.22,.61,.36,1),
              visibility 0s linear 280ms;
}

.new-creator.is-open {
  opacity: 1;
  visibility: visible;
  transform: translateX(0);
  transition: opacity 180ms ease, transform 280ms cubic-bezier(.22,.61,.36,1);
}

.phone-frame.is-landscape .new-creator {
  display: none;
}

.new-creator__close {
  position: absolute;
  top: 76px;
  right: 20px;
  z-index: 2;
  width: 40px;
  height: 40px;
  border: 0;
  background: transparent;
  color: #f7f7f8;
}

.new-creator__content {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 88px 16px 104px;
  text-align: center;
}

.new-creator__title {
  margin: 0 0 20px;
  font-size: 28px;
  line-height: 34px;
  font-weight: 700;
}

.new-creator__artwork {
  display: block;
  width: min(100%, 288px);
  margin: 0 auto;
  border-radius: 12px;
  object-fit: contain;
}

.new-creator[data-screen="library"] .new-creator__artwork {
  width: 158px;
  border-radius: 0;
}

.new-creator__description {
  margin: 18px auto 0;
  max-width: 340px;
  color: #b8b8c0;
  font-size: 17px;
  line-height: 24px;
}

.new-creator__dots {
  display: flex;
  justify-content: center;
  gap: 8px;
  min-height: 8px;
  margin-top: 16px;
}

.new-creator__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f7f7f8;
}

.new-creator__dot.is-active {
  background: #3567ff;
}

.new-creator__actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.new-creator__button {
  min-height: 48px;
  flex: 1 1 0;
  border: 0;
  border-radius: 8px;
  background: #282a30;
  color: #f7f7f8;
  font: 700 16px/20px var(--font-family-base);
}

.new-creator__button--primary {
  background: #3567ff;
}
```

Adjust only scoped `.new-creator` values during visual comparison. Do not
change shared home/player CSS. Keeping the overlay's bottom edge 90px above the
frame edge leaves the existing `.home-bottom-nav` visible and interactive,
with Moments retaining its current selected state.

- [ ] **Step 3: Load the new files**

After `css/create.css` in `index.html`, add:

```html
<link rel="stylesheet" href="css/new-creator.css?v=1" />
```

Immediately before `js/create.js`, add:

```html
<script src="js/new-creator.js?v=1" defer></script>
```

This order guarantees `window.NewCreatorFlow` is available by the time the
create-menu click handler runs.

- [ ] **Step 4: Run tests**

Run:

```bash
node --test tests/new-creator.test.js
node --check js/new-creator.js
```

Expected: state, index-wiring, and artwork tests PASS; syntax check exits 0.

### Task 4: Integrate the New Creator Menu Action Test-First

**Files:**
- Modify: `tests/new-creator.test.js`
- Modify: `js/create.js:4203-4238`

- [ ] **Step 1: Add a failing menu integration test**

Append to `tests/new-creator.test.js`:

```js
test('create menu places New Creator last and delegates to its flow', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'create.js'), 'utf8');
  const menuStart = source.indexOf('const MENU_ITEMS = [');
  const menuEnd = source.indexOf('];', menuStart);
  const menuSource = source.slice(menuStart, menuEnd);
  assert.match(menuSource, /id:\s*'new-creator'/);
  assert.ok(menuSource.lastIndexOf("id: 'new-creator'") > menuSource.lastIndexOf("id: 'album'"));
  assert.match(source, /window\.NewCreatorFlow\.open\(\)/);
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
node --test --test-name-pattern="create menu" tests/new-creator.test.js
```

Expected: FAIL because `new-creator` is absent from `MENU_ITEMS`.

- [ ] **Step 3: Add the last menu item and action**

Append this object after the existing `album` item in `MENU_ITEMS`:

```js
    { id: 'new-creator', label: 'New Creator', open: false, action: 'new-creator', icon:
      '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M6.25 3.75 7.188 2.5h5.624l.938 1.25h2.5A1.25 1.25 0 0 1 17.5 5v10a1.25 1.25 0 0 1-1.25 1.25H3.75A1.25 1.25 0 0 1 2.5 15V5a1.25 1.25 0 0 1 1.25-1.25h2.5Zm0 1.25h-2.5v10h12.5V5h-3.125l-.938-1.25H7.813L6.875 5H6.25ZM10 6.875A3.125 3.125 0 1 1 10 13.125 3.125 3.125 0 0 1 10 6.875Zm0 1.25a1.875 1.875 0 1 0 0 3.75 1.875 1.875 0 0 0 0-3.75Z"/></svg>' },
```

Update the item click handler to:

```js
      item.addEventListener('click', () => {
        hideCreateMenu();
        if (it.action === 'new-creator' &&
            window.NewCreatorFlow &&
            typeof window.NewCreatorFlow.open === 'function') {
          window.NewCreatorFlow.open();
          return;
        }
        if (it.open) open();
      });
```

- [ ] **Step 4: Run the complete automated checks**

Run:

```bash
node --test tests/new-creator.test.js
node --check js/new-creator.js
node --check js/create.js
```

Expected: all tests PASS and both syntax checks exit 0.

### Task 5: Browser Verification and Visual Refinement

**Files:**
- Modify if needed: `css/new-creator.css`
- Modify cache versions if CSS/JS changes: `index.html`

- [ ] **Step 1: Start the existing development server**

Before starting it, confirm port 8096 is not already serving this repository.
If it is not running:

```bash
python3 tools/serve.py
```

Expected: `http://localhost:8096/` becomes available.

- [ ] **Step 2: Verify the entry point**

At `http://localhost:8096/`:

1. Switch to mobile portrait and the Future Moments feed if necessary.
2. Tap the feed plus button.
3. Confirm **New Creator** is the last menu item with a Capture icon.
4. Confirm the existing Gallery item still opens the current creation flow.
5. Reopen the menu and select **New Creator**.

- [ ] **Step 3: Verify every path**

Check:

1. Library → How to Capture → Join.
2. Join → Continue → Enable.
3. Enable → Back → Join.
4. Enable → Continue → Capture.
5. Capture → Back → Enable.
6. Capture → Done → Moments feed.
7. Library → Back → Moments feed.
8. Close from each of the four screens → Moments feed.
9. Reopen after closing/completing → starts at Library.
10. Switch to landscape/desktop → flow cannot open.

- [ ] **Step 4: Compare each screen at 393 x 852**

Use the four supplied images as the source of truth. Refine only
`css/new-creator.css` until title position, artwork size, description wrapping,
buttons, dots, close control, and visible Moments bottom navigation align.

- [ ] **Step 5: Re-run verification after visual changes**

Run:

```bash
node --test tests/new-creator.test.js
node --check js/new-creator.js
node --check js/create.js
git diff --check
```

Expected: tests PASS, syntax checks exit 0, and `git diff --check` prints no
errors.

### Task 6: Add Go Capture and the RIVALS Entry Sheet

**Files:**
- Modify: `tests/new-creator.test.js`
- Modify: `js/new-creator.js`
- Modify: `css/new-creator.css`
- Modify cache version: `index.html`

- [ ] **Step 1: Add failing descriptor and DOM behavior tests**

Update the capture-screen descriptor expectation so its primary action is:

```js
{ label: 'Go Capture', action: 'go-capture', kind: 'primary' }
```

Extend the existing dependency-free VM/fake-DOM tests to exercise the real
browser branch:

```js
test('Go Capture closes guidance and immediately opens RIVALS entry', () => {
  const env = createBrowserEnvironment();
  env.window.NewCreatorFlow.open();
  env.advanceTo('capture');
  env.clickAction('go-capture');

  assert.equal(env.guidance.getAttribute('aria-hidden'), 'true');
  assert.equal(env.gameEntry.getAttribute('aria-hidden'), 'false');
  assert.equal(env.gameEntry.querySelector('.new-creator-game__title').textContent, 'RIVALS');
  assert.equal(env.document.activeElement, env.gameEntry.querySelector('.new-creator-game__play'));
});

test('ordinary guidance close does not open RIVALS entry', () => {
  const env = createBrowserEnvironment();
  env.window.NewCreatorFlow.open();
  env.clickAction('close');

  assert.equal(env.guidance.getAttribute('aria-hidden'), 'true');
  assert.equal(env.gameEntry, null);
});

test('Play dismisses RIVALS entry and returns focus', () => {
  const env = createBrowserEnvironment();
  env.openGameEntryFromCapture();
  env.gameEntry.querySelector('.new-creator-game__play').click();

  assert.equal(env.gameEntry.getAttribute('aria-hidden'), 'true');
  assert.equal(env.document.activeElement, env.preOpenFocus);
});

test('Escape dismisses RIVALS entry', () => {
  const env = createBrowserEnvironment();
  env.openGameEntryFromCapture();
  env.pressEscape();

  assert.equal(env.gameEntry.getAttribute('aria-hidden'), 'true');
});

test('game-entry backdrop does not dismiss the sheet', () => {
  const env = createBrowserEnvironment();
  env.openGameEntryFromCapture();
  env.gameEntry.querySelector('.new-creator-game__scrim').click();

  assert.equal(env.gameEntry.getAttribute('aria-hidden'), 'false');
});

test('incompatible device changes dismiss RIVALS entry', () => {
  const env = createBrowserEnvironment();
  env.openGameEntryFromCapture();
  env.changeDevice('desktop');

  assert.equal(env.gameEntry.getAttribute('aria-hidden'), 'true');
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
node --test --test-name-pattern="Go Capture|RIVALS|Play|backdrop|device changes" tests/new-creator.test.js
```

Expected: FAIL because the capture descriptor still says Done/close and the
RIVALS sheet does not exist.

- [ ] **Step 3: Change the final guidance action**

In `screens.capture.actions`, replace the primary descriptor with:

```js
Object.freeze({ label: 'Go Capture', action: 'go-capture', kind: 'primary' })
```

Handle it separately from ordinary close:

```js
if (action === 'go-capture') {
  close({ restoreFocus: false });
  openGameEntry();
  return;
}
```

Allow `close()` to suppress focus restoration during this handoff while
preserving all existing close behavior by default:

```js
function close(options = {}) {
  const restoreFocus = options.restoreFocus !== false;
  // Existing close/reset work.
  if (restoreFocus) restorePreviousFocus();
}
```

- [ ] **Step 4: Build the RIVALS entry DOM**

Add lazy `buildGameEntry(targetFrame)`, `openGameEntry()`, and
`closeGameEntry()` functions in `js/new-creator.js`.

The root is a non-modal section appended to `.phone-frame`:

```html
<section class="new-creator-game" role="dialog"
         aria-label="RIVALS game intro" aria-hidden="true">
  <div class="new-creator-game__scrim" aria-hidden="true"></div>
  <div class="new-creator-game__sheet">
    <span class="new-creator-game__handle" aria-hidden="true"></span>
    <div class="new-creator-game__identity">
      <img class="new-creator-game__thumb"
           src="assets/images/Game%20profile/rivals.webp?v=1" alt="">
      <div>
        <h2 class="new-creator-game__title">RIVALS</h2>
        <p class="new-creator-game__creator">
          Nosniy Games
          <span class="new-creator-game__verified" aria-label="Verified">✓</span>
        </p>
      </div>
    </div>
    <div class="new-creator-game__meta">
      <span>Maturity: Mild</span>
      <span aria-label="93 percent approval">👍 93%</span>
    </div>
    <button type="button" class="new-creator-game__play"
            aria-label="Play RIVALS">▶</button>
  </div>
</section>
```

Behavior requirements:

- `openGameEntry()` is mobile-portrait only, opens immediately after the
  guidance closes, sets `aria-hidden="false"`, and focuses Play.
- Play calls `closeGameEntry()`; the scrim has no dismissal handler.
- `closeGameEntry()` hides the sheet and restores the focus saved before the
  New Creator flow opened.
- Escape prioritizes closing the RIVALS entry before checking guidance.
- Device configuration, resize, and orientation reconciliation close either
  open surface.
- Ordinary Back/close paths never call `openGameEntry()`.

- [ ] **Step 5: Style the scrim and bottom sheet**

Append scoped rules to `css/new-creator.css`:

```css
.new-creator-game {
  position: absolute;
  inset: 0;
  z-index: 165;
  visibility: hidden;
  pointer-events: none;
}

.new-creator-game.is-open {
  visibility: visible;
  pointer-events: auto;
}

.new-creator-game__scrim {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.68);
  opacity: 0;
  transition: opacity 180ms ease;
}

.new-creator-game__sheet {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  min-height: 292px;
  padding: 10px 20px 22px;
  border-radius: 20px 20px 0 0;
  background: #1b1c20;
  transform: translateY(100%);
  transition: transform 280ms cubic-bezier(.22,.61,.36,1);
}

.new-creator-game.is-open .new-creator-game__scrim { opacity: 1; }
.new-creator-game.is-open .new-creator-game__sheet { transform: translateY(0); }
```

Complete the scoped rules to match the supplied reference:

- centered 40 x 4 drag handle;
- 56 x 56 rounded RIVALS thumbnail;
- 20px bold title and 15px muted creator;
- small blue verified badge;
- dark pill metadata chips;
- full-width 48px Roblox-blue Play button near the sheet bottom;
- focus-visible ring and reduced-motion overrides;
- `.phone-frame.is-landscape .new-creator-game { display: none; }`.

Do not modify shared feed/player CSS.

- [ ] **Step 6: Bump the cache version**

In `index.html`, increment only:

```html
<link rel="stylesheet" href="css/new-creator.css?v=2" />
<script src="js/new-creator.js?v=2" defer></script>
```

- [ ] **Step 7: Run automated verification**

Run:

```bash
node --test tests/new-creator.test.js
node --check js/new-creator.js
node --check js/create.js
git diff --check
```

Expected: all tests PASS, syntax checks exit 0, and no whitespace errors.

- [ ] **Step 8: Browser verification**

Serve the isolated feature worktree on an unused port and verify:

1. Final guidance CTA reads **Go Capture**.
2. It returns to the Moments feed and immediately opens the RIVALS sheet.
3. The sheet matches the supplied reference at 393 x 852.
4. Play and Escape dismiss it.
5. Back, X, and library Back never open it.
6. Backdrop taps do not dismiss it.
7. Desktop/landscape switches close or prevent the sheet.
8. Browser console has no errors.
