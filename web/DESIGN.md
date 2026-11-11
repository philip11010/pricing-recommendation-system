# Design system

Design documentation for the mentor-facing web application. This file is the
source of truth for colour, type, spacing, components, form patterns and chart
rules. It does not change any application code: where a token here differs from
what is currently in `tailwind.config.ts` or `src/app/globals.css`, this file
records the intended target and the code is migrated separately. The outstanding
migration work is listed in section 14.

The clickable reference for everything below is `web/design/mockups.html`. It
holds all eight screens behind a hash route, and its CSS custom properties are
the source for the token values in this file.

The product name is still being decided. Everywhere below, **[Product name]** is
a placeholder. The mockup prints a placeholder word in the brand slot purely so
the header is not empty, and that word carries no decision. The single place the
real name is written is the `BRAND` constant in `src/lib/copy.ts`, so renaming is
one edit.

## 1. What the interface is for

A mentor registers, receives a suggested session price in AUD, sees what similar
mentors charge, and accepts, changes or declines the suggestion. The audience is
non-technical professionals, on phones and laptops.

Two things follow from that, and they govern every decision in this file:

1. **The suggestion is advice.** The interface must never read as a verdict. The
   advisory sentence and the confidence note are first-class content, never fine
   print and never hidden behind a tooltip or a collapsed section.
2. **A number is the payload.** The price is the one thing a mentor came to
   read. Everything structural stays neutral so the eye lands on the figure.

### Two registers

The visual language has two registers, and every screen is assigned to one. Do
not blend them on a single screen.

| Register | Screens | Treatment |
|---|---|---|
| **Bold** | Landing, log in, the price hero | Full-bleed indigo and blue gradient, display type, one italic serif accent, white or outlined pill buttons, very little text |
| **Calm** | Register, similar mentors, directory, dashboard, add service, every chart and table | White, a slim gradient banner at the top only, one accent colour, neutral furniture, plain labels |

Section 12 assigns the register for each of the eight screens.

The price card is the hinge. It is a bold object and a calm object at once: a
plain white card, with the price on white, placed on the gradient. The gradient
never runs under the figure itself.

## 2. Colour tokens

### 2.1 Ink and surface

Unchanged by the move to indigo. These are the neutral furniture of the product.

| Token | Hex | Contrast on white | Used for |
|---|---|---|---|
| `ink-900` | `#0B0B0F` | 19.64:1 | Headlines, the price figure, body text, the current-price chart marker |
| `ink-700` | `#3F3F4A` | 10.39:1 | Secondary body text, card body copy |
| `ink-500` | `#55555F` | 7.37:1 | Helper text, axis labels, comparable dots, footer text |
| `surface` | `#FFFFFF` | n/a | Page background and card background. The page is white, not off-white |
| `surface-sunk` | `#F7F7F9` | 1.07:1 | Chart plot background, table stripes, disabled field fill |
| `line` | `#E4E4E9` | 1.27:1 | Card borders, field borders, dividers |
| `line-strong` | `#C9C9D2` | 1.64:1 | Field border on hover, chart axis line |

`ink-500` at 7.37:1 is the floor for any text in the product. There is no
lighter text token, because the next step down is where grey-on-grey starts.

There is no warm surface tint any more. The old `surface-warm` was an orange
wash and it is removed, not recoloured. Where a section needs a tinted
background instead of white, it uses one of the soft tints in section 2.4.

### 2.2 Accent

One accent family, indigo, used for actions and for the figure a mentor came to
read. A second hue, teal, is allowed for inline text links only, and nowhere
else. Every ratio below is measured, not inherited.

| Token | Hex | Contrast | Used for |
|---|---|---|---|
| `accent-700` | `#4338CA` | 7.90:1 on white, white on it 7.90:1 | Solid buttons, focus ring, the suggested-price marker, single-series chart lines, the active nav item |
| `accent-800` | `#312E81` | 11.42:1 on white, white on it 11.42:1 | Button hover and active, link hover on the accent, the dark end of gradients, label colour on a white pill over a gradient |
| `accent-100` | `#EEF2FF` | 1.12:1 on white. On it: accent-700 7.07:1, accent-800 10.21:1, ink-900 17.56:1, ink-700 9.29:1 | Selected row, active tab, chosen skill pill, stepper buttons, info callout fill |
| `link-700` | `#0F766E` | 5.48:1 on white | Inline text links in prose, on every screen |
| `link-800` | `#115E59` | 7.58:1 on white | Text link hover |

**Why a second hue for links only.** The solid primary button and an inline link
would otherwise be the same indigo, and on a form the two read as the same
offer. Teal separates "read more about this" from "do the thing". It is confined
to inline links and to the disclosure summaries that open a data table. It is
never a button fill, never a chart colour, and never a border.

On `accent-100` an inline link measures 4.90:1, which passes. On the stronger
soft tints it does not, so see the restriction in section 2.4.

### 2.3 Status

Unchanged. The caution amber stays, and it is what carries the low-confidence
note on a first estimate.

| Token | Hex | Fill | Contrast on its fill | Used for |
|---|---|---|---|---|
| `danger-700` | `#B3261E` | `#FFF1F0` | 5.94:1 | Validation errors, declined state |
| `success-700` | `#16704F` | `#EDF7F2` | 5.54:1 | Accepted state, saved confirmation, the Verified check mark |
| `caution-700` | `#8A5207` | `#FFF8E8` | 6.03:1 | The low-confidence note on a first estimate, the not-yet-verified chip |

Status colour is never the only signal. Every status carries an icon with a text
label, or a word.

### 2.4 Gradient and tints

The bold register is a gradient, not a set of glows on white. It is indigo and
blue led, and it is the only place in the product where large areas of colour
appear.

**Hero gradient** (landing, log in, the price hero, and the live price preview
panel on the register screen):

```
background:
  radial-gradient(45% 55% at 100% 100%, rgba(217, 70, 166, 0.75), transparent 70%),
  radial-gradient(45% 60% at 80% 55%,  rgba(6, 182, 212, 0.70), transparent 70%),
  radial-gradient(50% 60% at 45% 115%, rgba(124, 58, 237, 0.90), transparent 70%),
  linear-gradient(135deg, #1E1B8F 0%, #4338CA 50%, #2563EB 100%);
```

The linear base carries the meaning. The three radial glows, cyan `#06B6D4`,
violet `#7C3AED` and magenta `#D946A6`, sit low on the right and the bottom,
where there is no text. They are small, soft and late in the reading order of
the screen.

**Gradient banner** for calm screens, a slim band at the top of the page and
nothing below it:

```
background: linear-gradient(120deg, #1E1B8F, #4338CA 60%, #2563EB);
```

**Closing band** on the landing page, a rounded block inside the content column:

```
background: linear-gradient(120deg, #312E81, #4338CA 55%, #1D4ED8);
```

White text, and white pill buttons with an `accent-800` label at 11.42:1.

**Measured: white text on each gradient stop that carries text**

| Stop | Hex | White on it |
|---|---|---|
| Hero and banner dark end | `#1E1B8F` | 13.06:1 |
| Mid stop | `#4338CA` | 7.90:1 |
| Hero and banner light end | `#2563EB` | 5.17:1 |
| Closing band dark end | `#312E81` | 11.42:1 |
| Closing band light end | `#1D4ED8` | 6.70:1 |

Every stop clears 4.5:1 for white body text, so **white text is allowed anywhere
on the gradient**. The two tinted text colours are not, and that is the one
restriction:

- `#E0E7FF` lead paragraph: 10.60:1 on `#1E1B8F`, 6.41:1 on `#4338CA`, but
  **4.19:1 on `#2563EB`**, which fails.
- `#C7D2FE` fine print: 8.75:1 on `#1E1B8F`, 5.30:1 on `#4338CA`, but
  **3.46:1 on `#2563EB`**, which fails.

**Restriction.** Tinted text sits on the dark indigo area of the gradient only,
which in practice is the left and upper part of the hero and the whole of the
slim banner. Any text that would travel into the blue end of the gradient is
white, or it moves onto a card.

**Soft tints** for content cards on calm screens and for the landing step cards.
Always with ink text, never with white text, and never behind a chart.

| Tint | Hex | ink-900 on it | ink-700 on it | ink-500 on it | accent-800 on it |
|---|---|---|---|---|---|
| Indigo | `#E0E7FF` | 15.94:1 | 8.43:1 | 5.98:1 | 9.27:1 |
| Blue | `#DBEAFE` | 16.10:1 | 8.52:1 | 6.04:1 | 9.36:1 |
| Violet | `#EDE9FE` | 16.55:1 | 8.75:1 | 6.20:1 | 9.62:1 |
| Cyan | `#CFFAFE` | 17.55:1 | 9.28:1 | 6.58:1 | 10.20:1 |

**Restriction on links over a tint.** `link-700` measures 4.44:1 on `#E0E7FF`
and 4.49:1 on `#DBEAFE`. Both fail 4.5:1. It passes on `#EDE9FE` at 4.61:1 and
on `#CFFAFE` at 4.89:1. Because two of the four fail, **inline links do not sit
on a soft tint at all**. A tinted card that needs a link ends with the link on
white, or the card carries the destination as a pill button instead.

**Glow and gradient rules**

- Bold screens carry a **full-bleed gradient**: landing hero, log in, the price
  hero. Calm screens carry the **slim banner** at the top and white underneath.
  There is no third option.
- A decorative blurred glow is still allowed, as an absolutely positioned
  ellipse with `filter: blur(110px)`, `opacity` near `0.28`,
  `pointer-events: none` and `aria-hidden="true"`. It is used behind the tinted
  step cards on the landing page, and it is clear of every line of text.
- **Text never sits on a light or mid-tone glow.** Either the glow is clear of
  the text entirely, or the text sits on a card at full opacity that covers the
  glow. No translucent card over a glow behind running text.
- Charts, forms and tables sit on white, with no gradient and no glow behind
  them. The banner stops where the content starts.
- The gradient and the glows do not drift, pulse or animate, anywhere, and they
  are static under `prefers-reduced-motion: reduce` as well.
- The glow hues are decoration by arithmetic as well as by rule. Measured on
  white, cyan `#06B6D4` is 2.43:1 and magenta `#D946A6` is 3.90:1, so neither
  can carry text. Violet `#7C3AED` at 5.70:1 and blue `#2563EB` at 5.17:1 would
  pass, and they are still never used for text, an icon, a border or a chart
  mark, because the product has one accent.

### 2.5 Token discipline

Components reference tokens, never raw hex. Every value above becomes a Tailwind
theme entry and a CSS custom property, including the gradient recipes, which
become one property each. A hex literal in a component file is a defect,
including in chart props.

## 3. Typography

Three families, all free, all loaded through `next/font/google` in the root
layout so they are self-hosted and cost no layout shift. One `variable` per
family, applied on `<html>`.

| Role | Family | Weights | Variable |
|---|---|---|---|
| Display | **Inter Tight** | 800 | `--font-display` |
| Body and UI | **Inter** | 400, 500, 600, 700 | `--font-sans` |
| Accent | **Playfair Display** | 500 italic only | `--font-accent` |

Inter Tight is the heavy modern headline voice. It is a sibling of Inter, so the
display and the body do not argue with each other, and its tighter widths let a
long headline hold a large size on a phone. Playfair Display italic is the
elegant counterpoint. Both are variable fonts, so one file per family covers
every weight used.

**The accent rule.** Playfair Display italic is used for **one or two words per
page, at most, and only inside a display-size heading**. It is never used for
body text, labels, buttons, numbers, or anything in a chart. Because its
lowercase reads smaller than Inter Tight at the same size, set it at `1.06em`
relative to the heading it sits in, and keep it on the same baseline.

### 3.1 Type scale

| Token | Size | Line height | Tracking | Family and weight |
|---|---|---|---|---|
| `display-xl` | `clamp(2.5rem, 7vw, 4.5rem)` | 1.02 | -0.03em | Inter Tight 800 |
| `display` | `clamp(2rem, 6vw, 3.25rem)` | 1.08 | -0.025em | Inter Tight 800 |
| `display-sm` | `clamp(1.75rem, 5vw, 2.5rem)` | 1.08 | -0.025em | Inter Tight 800, the banner heading on calm screens |
| `figure` | `clamp(2.5rem, 9vw, 4rem)` | 1.00 | -0.03em | Inter Tight 800, tabular numerals |
| `h2` | `clamp(1.375rem, 3vw, 1.75rem)` | 1.20 | -0.015em | Inter 700 |
| `h3` | `1.125rem` | 1.30 | -0.01em | Inter 600 |
| `body-lg` | `1.125rem` | 1.60 | 0 | Inter 400 |
| `body` | `1rem` | 1.55 | 0 | Inter 400 |
| `small` | `0.875rem` | 1.50 | 0 | Inter 400 |
| `label` | `0.8125rem` | 1.40 | 0.01em | Inter 600 |
| `overline` | `0.75rem` | 1.30 | 0.08em | Inter 700, uppercase |

- Body text is 16px. Nothing in the product is below 12px, and 12px is only the
  `overline`, which is never running prose.
- `display-xl` is the landing hero only, once per site.
- `display-sm` is the heading inside a gradient banner, so a calm screen never
  opens at hero size.
- `figure` is the price, and only the price. It always uses tabular numerals so
  a changing number does not shuffle the layout.
- Prose is capped at `68ch`, and the lead paragraph on a gradient at `46ch`.
  Headlines are capped at `20ch` with `text-wrap: balance`, which is a visual
  improvement and not a guarantee of a particular final line, so every headline
  is checked at 320px, 768px and 1440px with its natural wrap as the fallback.
  No forced line breaks and no hardcoded non-breaking spaces.
- Fluid sizes, unitless line heights, and no fixed-height text containers, so
  text still reflows at 200 percent zoom and under user spacing overrides.

## 4. Spacing, radius, elevation

### 4.1 Spacing

A 4px base, standard density. Use only these steps.

| Token | Value | Typical use |
|---|---|---|
| `space-1` | 4px | Icon to its label |
| `space-2` | 8px | Minimum gap between two adjacent targets |
| `space-3` | 12px | Label to field |
| `space-4` | 16px | Page gutter on a phone, padding inside a compact card |
| `space-6` | 24px | Card padding, gap between fields |
| `space-8` | 32px | Gap between field groups, card padding on desktop |
| `space-12` | 48px | Gap between sections on a calm page |
| `space-16` | 64px | Section rhythm on a bold page |
| `space-24` | 96px | Landing hero breathing room, desktop only |

Page gutter: 16px at phone widths, 24px from 640px, with the content column
capped at 1024px for application pages and 1152px for the landing page. The
gradient is full bleed; the column inside it still obeys these caps.

### 4.2 Radius

| Token | Value | Applied to |
|---|---|---|
| `radius-pill` | 9999px | All buttons, badges, chips, segmented controls |
| `radius-card` | 20px | Cards, the price card, form sections, modals |
| `radius-band` | 28px | The closing gradient band on the landing page |
| `radius-chart` | 16px | Chart container |
| `radius-field` | 12px | Inputs, selects, textareas |
| `radius-bar` | 6px | Bar and ladder ends inside a chart |

Pill for anything you press, soft rectangle for anything that holds content. No
other radii, and no square corners anywhere.

### 4.3 Elevation

One shadow, used sparingly.

```
shadow-card: 0 1px 2px rgba(11, 11, 15, 0.04),
             0 8px 24px -12px rgba(11, 11, 15, 0.18)
```

Cards on a calm page use a `1px` `line` border and no shadow. A card sitting on
the gradient uses `shadow-card` and no border, because a border would compete
with the colour behind it. Nothing else is raised.

## 5. Buttons

Minimum interactive height 44px on touch and 40px on pointer. No target is
smaller than 24 by 24 CSS px in any case, and adjacent targets are at least 8px
apart. Every button is a real `<button>` or `<a>`, shows `cursor: pointer`, and
transitions `background-color`, `border-color` and `color` over 180ms.

| Variant | Where | Style |
|---|---|---|
| **White pill** (bold default) | On the gradient: landing hero, closing band, dashboard banner | White fill, `accent-800` label at 11.42:1, no border. Hover fills `#E0E7FF` |
| **Outlined pill on dark** | The secondary action beside a white pill | Transparent fill, `2px` white border, white label. Hover fills white with an `accent-800` label |
| **Outlined pill on white** | A secondary action on a calm screen | Transparent fill, `2px` `ink-900` border, `ink-900` label. Hover fills `ink-900` with a white label |
| **Solid pill** (calm default) | Form submit, accept the suggestion, log in | `accent-700` fill, white label at 7.90:1, no border. Hover `accent-800` at 11.42:1 |
| **Quiet pill** | Change, Decline, Back, Add a service from a table | Transparent fill, `1px` `line` border, `ink-700` label. Hover `surface-sunk` fill and `line-strong` border |
| **Text link** | Inline in prose, and the data table disclosure | `link-700`, underlined with a 2px offset. Hover `link-800`. On the gradient it is white with an underline instead. Never a bare colour change as the only cue |

One primary action per view. On the price card the three actions are Accept
(solid), Change (quiet), Decline (quiet), in that order, stacked full width
below 560px and in a row above it.

A solid pill keeps `accent-700` even inside a card on the gradient. The card is
white, so the button's own 7.90:1 still holds and the card does not need a
different button set from the rest of the product.

Destructive and irreversible actions are never the solid primary. Declining a
suggestion is reversible, so it is a quiet pill and not a red one.

**Icons in buttons.** Icons are SVG from one family per surface, Phosphor
preferred with Heroicons as the fallback, at 20px for controls. No emoji, ever.
A decorative icon beside a visible label is `aria-hidden="true"`. An icon-only
button is only allowed for standard navigation, and it always carries an
accessible name.

### 5.1 Focus

```
:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px #FFFFFF, 0 0 0 4px #4338CA;
}
```

On the gradient the ring inverts, so it is still visible against indigo:

```
.on-gradient :focus-visible {
  box-shadow: 0 0 0 2px #1E1B8F, 0 0 0 4px #FFFFFF;
}
```

A control inside a white card reverts to the indigo ring, even when that card is
on the gradient. Measured: the indigo ring is 7.90:1 against white, and the white
ring is 13.06:1 against `#1E1B8F`. Both are far above the 3:1 a non-text
indicator needs.

- Visible on every operable control, including controls inside a modal and
  controls sitting on the gradient.
- Never removed without a replacement of at least equal visibility.
- The sticky header offsets focus with `scroll-padding-top: var(--header-height)`
  so a focused control is never fully hidden behind it.
- Tab order follows visual order. Every action is reachable and completable
  without a pointer.

## 6. Cards

| Card | Register | Composition |
|---|---|---|
| **Price card** | Bold | `radius-card`, white at full opacity, `shadow-card`, placed on the gradient. Contents in order: overline label, the `figure` price, the range beneath it, the ladder if present, the plain-language sentence, the confidence note if present, the three actions, then the optional set-your-own-price field |
| **Content card** | Calm | White, `1px` `line`, `radius-card`, `space-6` padding, `h3` heading, `body` copy |
| **Tinted card** | Calm | One of the four soft tints, no border, `radius-card`, ink text only, used for the landing step cards and nowhere a link is needed |
| **Statistic card** | Calm | White, `1px` `line`, label in `overline` above a value with tabular numerals, optional `small` note. Used instead of a chart when there are fewer than four data points |
| **Mentor card** | Calm | White, `1px` `line`, `radius-card`. Avatar on a soft tint with an `accent-800` monogram at 9.62:1, name, service, the verification chip, the field chip, then the price and the review count on the bottom row |
| **Chart card** | Calm | White, `1px` `line`, `radius-chart`, heading, the plain-language sentence, the chart, then the data table disclosure |

The price card is the only place in the product where the gradient and a large
number meet, and the number sits on white inside the card, never on the
gradient.

## 7. Form patterns

The registration form is calm. The gradient appears only in the banner at the
top of the page and inside the live price preview panel beside the form.

### 7.1 Field anatomy

Top to bottom, always in this order:

1. **Label**, `label` token, visible, always present, a `<label for>` bound to
   the input. A placeholder is never the label. Placeholders are only used for a
   format example, such as `e.g. 45`.
2. **Helper text**, `small` in `ink-500`, directly under the label and above the
   input, so it is read before the field is answered rather than after.
3. **Input**, `radius-field`, `1px` `line` border, 44px minimum height, 16px
   text so iOS does not zoom on focus, `surface-sunk` fill when disabled.
4. **Error**, `small` in `danger-700` with a warning icon, immediately below the
   input, bound with `aria-describedby`, and the input gets
   `aria-invalid="true"`.

A fixed-height slot is reserved for the error line, so showing it does not push
the rest of the form down.

**Choice controls.** A small bounded number, such as how many people are in a
session, uses a stepper: a pill-shaped group with a minus button, an `output`
with `aria-live="polite"`, and a plus button. The buttons are 40px circles
filled `accent-100` with an `accent-800` glyph at 10.21:1, and they clamp at the
ends of the range rather than disappearing. A multiple-choice set, such as the
skills, uses pill checkboxes: a real `<input type="checkbox">` that is visually
hidden but still focusable, with the pill as its label. A chosen pill is
`accent-100` fill, `accent-700` border and an `accent-800` label at 10.21:1, so
the selection is carried by fill, border and weight together and not by colour
alone.

### 7.2 Validation and feedback

- Validate on blur for most fields, not only on submit.
- On a failed submit, render a focusable error summary at the top of the form:
  `role="alert"`, `tabindex="-1"`, a heading, and one link per problem that jumps
  to its field. Move focus to it. **Keep the inline errors as well.** The summary
  complements them and never replaces them.
- Submitting shows a loading state on the button with `aria-busy`, then a success
  or error result. The layout does not shift between the three states.
- Money fields are labelled in AUD at the field, not only in a page heading.
  There is no currency conversion anywhere in the product.
- Every list that can come back empty has an empty state with a sentence and the
  next action, never blank space.

### 7.3 Grouped collapsible sections

Long forms are grouped rather than paged, so a mentor can see how much is left.

- Group into named sections with an `h3` heading and a one-line description.
- Sections containing required fields are **expanded by default**. A required
  field is never hidden behind a collapsed section.
- Optional sections start collapsed, with a summary line stating what is inside
  and why it helps, for example "Optional. Adds to your public profile. Shown on
  your card, not used in the price."
- The trigger is a full-width `<button>` with `aria-expanded` and
  `aria-controls`, a chevron that rotates over 180ms, and a 44px minimum height.
  The whole header row is the target, not just the chevron.
- A collapsed section that contains an error expands automatically on a failed
  submit, and its error is counted in the summary at the top.
- Collapsing is a layout change, so the height transition is 180ms and is
  disabled under `prefers-reduced-motion: reduce`.

## 8. Chart rules

The library is Recharts, already in the project. Charts live on calm surfaces
only, on white, with no gradient and no tint behind them.

### 8.1 Which chart does which job

| Job | Chart | Why, and when not to use it |
|---|---|---|
| Where the suggested price sits against what similar mentors charge | **Price ladder**: a horizontal low-to-high track, a shaded band for the middle of the group, a marker for the suggested price and a marker for the current price | This is a performance-against-range question, so the bullet-chart form is right: it reads at a glance, fits a phone, and needs no legend. Do not use a gauge or a dial, which spend a lot of space on one number and imply a score |
| What individual similar mentors charge | **Dot strip**: one dot per comparable mentor on the same horizontal price axis, with this mentor's own price shown as a distinct ring and a labelled leader line | A short, unaggregated set is better shown as the actual points than summarised. Do not use a box plot: it needs roughly 20 points per group to mean anything, and it assumes a statistical reader. Do not use a histogram with fewer than about 15 comparable mentors, because the shape then comes from the bin width rather than from the data |
| The headline answer | **A plain-language sentence**, not a chart | One number with one comparison is a sentence, and a sentence is readable by everyone. The sentence is mandatory and sits above the chart, not below it |
| A mentor's price over months | **Line chart**, one series, visible point markers | A continuous time axis read for direction. Below four months, show a statistic card instead: a line through three points invents a trend |
| A mentor's sessions or reviews per month | **Bar chart**, vertical, one series | Discrete per-month tallies, which are counts rather than a continuous quantity |
| Any single value with no comparison | **Statistic card** | A chart with one mark is decoration |

### 8.2 Colour in charts

Charts use ink, neutrals, one accent, and one cool band fill with a dark edge.
No gradient fills, no glow hues, no second series hue.

| Element | Token | Measured |
|---|---|---|
| Ladder track | `#F1F1F4` | 1.13:1 on white, so it always carries end labels |
| Typical band fill | `#BAE6FD` | 1.33:1 on white, 1.18:1 against the track |
| Band edge rules | `#0369A1`, 2px | 5.93:1 on white, 5.26:1 against the track, 4.47:1 against the band fill |
| Suggested price marker | `accent-700` `#4338CA`, filled triangle | 7.01:1 on the track, 5.96:1 on the band |
| Current price marker | `ink-900` `#0B0B0F`, open circle with a 2px stroke | 17.43:1 on the track, 14.80:1 on the band |
| Comparable dots | `ink-500` `#55555F` | 7.37:1 on white |
| This mentor's dot | `accent-700` ring, larger radius, with a label and a leader line | 7.90:1 on white |
| Line and bar series | `accent-700`, 2.5px line or a 100 percent bar fill | 7.90:1 on white |
| Second series, if ever needed | `ink-500`, dashed, with a direct end label | 7.37:1 on white |
| Axis line | `line-strong` `#C9C9D2` | 1.64:1 |
| Gridlines | `#EDEDF1`, horizontal only | 1.17:1 |
| Axis and tick labels | `ink-500` | 7.37:1 |

**The honest limitation, stated as a rule.** The band fill measures 1.18:1
against the track, which is nowhere near 3:1. A pale band and a pale neutral
track are close in luminance by construction. The band is therefore **never
identified by its fill alone**. It is identified by three things at once: the
fill, the two 2px edge rules at `#0369A1`, and a visible text label carrying both
end values. The edges themselves do clear the 3:1 a non-text indicator needs,
at 4.47:1 against the band and 5.26:1 against the track, so the shape of the band
survives in greyscale even where the fill does not. The same belt-and-braces
applies to the two markers, which differ in shape, a filled triangle against an
open circle, as well as in colour, and both carry a text label. This is the only
configuration that works for a colour-blind reader and in greyscale.

### 8.3 Labels

- Every chart has a visible `h3` heading and the plain-language sentence above
  it. The sentence states the answer in words.
- Direct labels on the marks, not a legend, wherever there are three or fewer
  series. A one-series chart never gets a legend. The ladder carries a small
  swatch legend instead, because its three elements are a shape, a shape and a
  band rather than three series.
- Price axis ticks are whole AUD with a thousands separator and no decimals, for
  example `$240`. Currency is stated once, in the axis title or the heading, and
  not repeated on every tick.
- Tick labels never rotate past 45 degrees. If they would have to, the chart
  becomes horizontal instead.
- A value shown on hover is also shown on keyboard focus, and the same values
  appear in the table below.
- Band and marker labels are short and stay whole. A compact label does not wrap
  to a second line, and truncation is never recovered by a hover-only tooltip.

### 8.4 Chart accessibility

- Every chart is followed by a disclosure containing the same data as a real
  `<table>` with a caption. The disclosure is a `<details>` or a button with
  `aria-expanded`, so it is operable rather than a hidden div.
- An `sr-only` summary sentence precedes the chart, and the chart wrapper is
  `role="img"` with an `aria-label` that states the answer, not the chart type.
- Focus moves through the interactive marks in reading order, and focus on a mark
  reveals exactly what hover reveals.
- Recharts animation is off, or at minimum disabled under
  `prefers-reduced-motion: reduce`. An animated chart delays the number a mentor
  came for.
- Chart containers are responsive with a reserved aspect ratio, so the page does
  not shift when the chart mounts. Minimum chart height 180px, and the ladder
  stays legible at 320px wide.
- No chart relies on colour alone for any distinction, anywhere.

## 9. Motion

Subtle tier. Motion exists to show where something came from, never to decorate.

- Durations: 120ms for a press, 180ms for hover and colour, 220ms for a panel or
  a disclosure, 300ms for a route-level fade. Not one duration for everything.
- Easing `cubic-bezier(0.25, 0.46, 0.45, 0.94)` for entrances, and exits are
  faster than entrances.
- Animate `opacity` and `transform` only. Never `width`, `height`, `top` or
  `left`.
- A reveal is a fade with an 8px to 12px rise, so it reads as a fade and not a
  slide. One or two animated elements per view at most.
- The gradient is static. It does not shift, rotate or animate on load, on
  scroll or on hover.
- `prefers-reduced-motion: reduce` collapses every transition and animation to
  near zero and renders the final state immediately. This is already in
  `globals.css`, and it applies to Recharts, the stepper and the disclosures.
- Nothing below the fold is invisible by default without a no-JS fallback.
- CSS transitions cover all of the above. The project needs no animation library
  for this design system.

## 10. Responsive

Mobile first. Breakpoints 375, 560, 640, 768, 900, 1024, 1440, tested at each.

- `width=device-width, initial-scale=1`, and user zoom is never disabled.
- No horizontal page scroll at any width. The content column is a fluid
  `min(100%, cap)`, never a fixed pixel width. The gradient is full bleed and
  `overflow-x` is hidden on the body so a glow cannot create a scrollbar.
- At 900px and below: the hero stacks to one column with the price card beneath
  the headline, the register form drops its sticky preview to a static block
  below the form, and two-column chart rows become one.
- At 560px and below: actions stack full width, three and four column grids
  become one, the ladder stays horizontal, and the dot strip stays horizontal and
  scrolls only inside its own container, with a visible affordance.
- Tables scroll inside a labelled, focusable container, never by moving the page.
- Images and media carry an `aspect-ratio` so nothing shifts as they load, and
  below-the-fold media is lazy loaded.
- The landing hero uses `display` rather than `display-xl` below 640px. The
  gradient itself does not change between breakpoints.
- The gradient banner keeps its vertical padding on a phone, so a calm screen
  still opens with a band of colour rather than a cramped stripe.

## 11. Do and do not

**Do**

- Put the plain-language sentence before the chart, every time.
- Keep the price on white, inside a card, at `figure` size with tabular numerals.
- Keep the advisory sentence and the confidence note visible, at full size.
- Use one accent for actions and the price, and teal for inline links only.
- Keep white text on the dark indigo part of the gradient, and move tinted text
  off the blue end.
- Label every band, marker and series in text as well as in colour.
- Give every chart a real data table.
- Reserve space for anything that appears later: errors, badges, charts.
- Keep the registration form plain and grouped, with required sections open.
- Give every control a visible focus ring and a 44px touch height.
- Show a statistic card when there are fewer than four points.

**Do not**

- Do not set text, a number or an icon on a light or mid-tone glow.
- Do not put an inline link on a soft tint.
- Do not use cyan, violet or magenta for text, borders, icons or chart marks.
- Do not put the gradient behind a form, a table or a chart.
- Do not add a third hue, a gradient chart fill or a second chart accent.
- Do not use the italic serif for more than two words on a page, or below display
  size.
- Do not use a gauge, a dial, a pie or a donut anywhere in this product.
- Do not animate a chart, the gradient, or anything on load.
- Do not hide a required field, an error or the confidence note behind a
  collapsed section or a hover-only tooltip.
- Do not replace inline field errors with a summary at the top.
- Do not use a placeholder as a label.
- Do not use emoji as icons.
- Do not write a raw hex value in a component.
- Do not hard-code the product name outside the `BRAND` constant.

## 12. Screens

Eight screens, each assigned to one register. The mockup routes them by hash in
the order below.

### 12.1 Landing, bold

The first impression and the argument for registering. Full-bleed hero gradient
with the headline, the lead, a white primary pill to register and a text link
for an existing mentor, beside an example price card. Below the hero: a three
step explanation on soft tinted cards over two soft glows, a row of three mentor
cards with a link to the full directory, a closing gradient band with two pill
buttons, and a one-line footer that restates that the price is advisory and in
Australian dollars.

### 12.2 Log in, bold

Returning to an existing profile. The hero gradient fills the viewport and holds
one centred white card: email, password, a full-width solid pill, and a text
link to register. Nothing else competes with it.

### 12.3 Register, calm with a banner

Creating a profile and reaching a first price. A slim gradient banner carries the
heading and a one-line promise, then the form sits on white in two columns.

Registration has four parts, in this order:

1. **Your account.** Full name, email, password.
2. **What you offer.** The field, as a select, and how many people per session,
   as a stepper from 1 to 8. This part does most of the work in the price.
3. **Skills you cover.** Pill checkboxes, grouped, see 12.3.1.
4. **More about you.** Optional, and collapsed by default. Years of experience,
   education and credentials. The summary line states that these go on the public
   profile and are not used in the price.

There is no "services planned" field. A new profile starts **unverified** and
says so in plain words under the submit button. A **Verified** check mark with a
visible text label appears on the mentor card only once the details are
confirmed, never on a brand new profile.

#### 12.3.1 Skill groups

All 30 skills are shown, none removed, in four named groups:

| Group | Count |
|---|---|
| Getting hired | 7 |
| Growing your career | 8 |
| Skills at work | 10 |
| Business and balance | 5 |

The group name is an `overline`, and the skills inside it are pill checkboxes
that wrap. Grouping is what makes 30 options readable; hiding some of them is
not.

#### 12.3.2 Live price preview

Beside the form, a sticky panel with the gradient as its background and a white
card inside it, showing the price so far and how it changes with group size. It
sticks to the top of the viewport on desktop and **stacks below the form on
phones**, where sticky would cover the field being answered. It is explicitly
labelled as a preview, with the full suggestion coming on the next screen.

### 12.4 Price, bold hero then calm

The payload screen. The hero gradient holds the headline, one line on what the
price was based on, and the price card: overline, the figure in AUD with the
group size, the range, the advisory sentence, the low-confidence note when it
applies, Accept, Change and Decline, and a field to set your own price instead.

Below the gradient, on white, two calm cards side by side. Each one opens with a
plain-language sentence, then the visual:

- **Where your price sits**, a price ladder with the band, the suggested marker
  and a swatch legend.
- **Mentors like you**, a dot strip of comparable mentors with this mentor's own
  price ringed and labelled, and a link to the full list.

### 12.5 Similar mentors, calm

What comparable mentors charge, and on what basis they were matched. Gradient
banner, then a filter group of toggles for the match rules, a summary sentence
in bold prose, the dot strip at full width, and a table of the comparable
mentors. Individual mentors are not named in this view, and the page says why.

### 12.6 Directory, calm

Browsing who is on the platform. Gradient banner, a row of field filters as
toggles, then a responsive grid of mentor cards. Each card carries the avatar,
the name, the service, the verification chip, the field chip, the price and the
review count. A mentor with no reviews yet says so rather than showing a zero.

### 12.7 Dashboard, calm

How a mentor's price and demand have moved. The gradient banner carries the
greeting and a white pill to add a service. On white below it:

1. **Four headline statistics**: the current price, the typical price for similar
   mentors, reviews this year, and the share of available days booked.
2. **How you compare**, a sentence followed by the ladder with the current-price
   marker, so the comparison is read in words first.
3. **Your price through the year**, a one-series line chart with twelve points
   and a data table.
4. **Reviews each month**, a one-series bar chart with twelve bars and a data
   table.
5. **Your services**, a table of each service with its own price, the suggested
   price and the decision, shown as an Accepted, Pending or Declined chip with a
   text label.

### 12.8 Add service, calm

Getting a price for something new. Gradient banner, then a single narrow form:
service name, how many people per session, and which of the mentor's own skills
it covers. Submitting goes to the price screen.

### 12.9 Navigation

The header is dark on bold screens and white with a bottom border on calm
screens. The brand mark sits left, the navigation right.

**Visitors** see: Browse mentors, Existing mentor as an outlined pill, Register
as a solid pill. The text link collapses first on a phone; the two pills do not.

**Logged-in mentors** see: Mentors, Dashboard, Log out, and an avatar monogram.
The current page is marked with `aria-current="page"` and rendered in
`accent-700` at 7.90:1, with a weight change as well, so the current item is not
signalled by colour alone.

## 13. Anti-patterns flagged for this product

These are the anti-patterns the design research flags for a professional,
advisory, trust-carrying product, filtered to the ones that can actually happen
here, with what we do about each.

1. **Generic purple and pink gradient wash.** Flagged against every professional
   and advisory product profile, because it reads as a template. The resolution
   is in which hues lead. The gradient is **indigo and blue led**: its linear
   base runs `#1E1B8F` to `#4338CA` to `#2563EB`, which is the accent family
   itself, so the colour on the bold screens is the same colour as the buttons on
   the calm ones. Violet, magenta and cyan appear only as small, soft radial
   glows low on the right and the bottom, late in the reading order and clear of
   every line of text. A reader sees an indigo product with a warm tail, not a
   purple to pink wash. See section 2.4.
2. **Playful design.** Bold is not playful. No bounce, no spring, no mascot, no
   confetti on acceptance, and no exclamation marks in price copy.
3. **Hidden or buried terms.** The advisory nature, the price range and the
   low-confidence note are visible content at full size. Nothing a mentor needs
   in order to judge the number is collapsed, greyed out, or deferred to a
   tooltip.
4. **Removing the focus ring.** Any `outline: none` without an equally visible
   replacement is a defect. On the gradient the ring inverts rather than
   disappearing.
5. **Placeholder as the only label.** Every input has a visible bound label.
6. **Errors only in a summary at the top.** The summary complements inline errors
   and never replaces them.
7. **Icon-only buttons with no accessible name.**
8. **Emoji used as icons.**
9. **Grey text on a grey background.** `ink-500` at 7.37:1 is the lightest text
   in the product.
10. **Light text on the light end of a gradient.** Measured and restricted in
    section 2.4: tinted text stays on the dark indigo area, and anything that
    would travel into `#2563EB` is white or moves onto a card.
11. **Colour as the only carrier of meaning in a chart.** Addressed by shape,
    direct labels and the data table in section 8.
12. **One duration for every transition, and animating `width` or `height`.**
13. **Ignoring `prefers-reduced-motion`.**
14. **Overwhelming a mentor with every field at once.** Addressed by the four
    grouped parts in section 12.3 and the skill groups in 12.3.1, without hiding
    anything required.
15. **Content jumping when validation text, a badge or a chart appears.** Space
    is reserved.
16. **Hover-only disclosure.** Anything revealed on hover is revealed on focus
    and on touch.
17. **A compact label wrapping to a second line**, or clipping with only a
    `title` attribute to recover it.
18. **Mixing visual registers on one screen.** Bold and calm are assigned per
    screen in section 12.
19. **Fixed pixel container widths, and disabling zoom.**
20. **A chart built from fewer than four points.** Use a statistic card.
21. **Raw hex in components** instead of the tokens in section 2.

## 14. Deferred build work

Recorded here so the gap between this document and the running application is
explicit. None of it is in scope for this documentation change, and the code
still carries the previous teal and orange palette until each item is picked up.

- Migrate the Tailwind theme and `globals.css` tokens from teal and orange to the
  values in section 2, including the three gradient recipes and the four soft
  tints.
- Log in and log out, with hashed passwords.
- A public mentors list endpoint for the directory and the landing page row.
- A stateless live price preview endpoint for the register screen, taking the
  partial form state and returning a provisional figure.
- A price and reviews history series for the demo mentors, so the dashboard
  charts have twelve real points each.
- About 10 demo mentors, enough to fill the directory grid and the comparables
  table.
- Rebuild the eight screens to match the mockup, register by register.
- Update the Playwright specs to the new navigation, the four-part registration
  form and the new screen set.
