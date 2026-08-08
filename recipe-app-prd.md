# PRD — TableStory Recipe App Rebrand

**Version:** 1.0  
**Owner:** Product team, Hearth & Harvest Foods  
**Status:** Approved for workshop planning  
**Target product:** Existing Pocket Cinema demo application  
**Target release:** Workshop demonstration release

## Executive summary

Hearth & Harvest Foods wants to use the Pocket Cinema application as the technical foundation for **TableStory**, a recipe discovery app for home cooks. The existing application already provides useful responsive browsing, detail pages, saved-item behavior, search, and television remote navigation. However, its product identity, information architecture, content model, routes, API language, and interaction copy are entirely based on films.

This project is therefore a **complete product rebrand and domain conversion**, not a logo swap. Every customer-visible reference to cinema must be replaced with a coherent cooking experience, and the underlying interfaces must describe recipes rather than disguising recipes as movies.

The result should feel like a deliberately designed recipe product on both mobile and television while remaining small enough to build and verify during the Software (re)-Factory workshop.

## Problem and opportunity

Hearth & Harvest currently publishes recipes across social posts and PDF leaflets. Customers cannot search the collection, save dishes for later, or comfortably follow a recipe from a television in the kitchen. Building a new application from scratch would repeat capabilities already demonstrated by Pocket Cinema.

Simply replacing movie titles with recipe names would leave film-specific URLs, fields, labels, and mental models throughout the product. Terms such as “films,” “genres,” “runtime,” “rating,” and “watchlist” would make the experience confusing and undermine the new brand. A total rebrand is justified because the product must communicate a different purpose at every layer:

- People discover dishes, not films.
- Recipe cards emphasize preparation time, difficulty, and dietary tags rather than year, runtime, and age rating.
- Recipe details provide ingredients and ordered cooking steps rather than a synopsis.
- People save recipes to **My Cookbook**, not a watchlist.
- Browsing groups recipes by meal occasion and dietary need, not film genre.
- The visual identity must evoke a warm, practical kitchen rather than a dark streaming service.

## Product goal

Transform Pocket Cinema into TableStory, a responsive recipe discovery experience in which a home cook can find a suitable recipe, understand what it requires, save it, and read the cooking method from either a phone or a TV remote.

The workshop succeeds when an attendee can inspect the finished application without finding any Pocket Cinema or movie-domain language in the supported user experience or public API.

## Users

### Primary user: everyday home cook

A time-conscious person looking for an appealing recipe based on a dish name, ingredient, meal type, or dietary preference. They need useful information at a glance and a clear recipe they can follow.

### Secondary user: hands-busy kitchen viewer

A person displaying a recipe on a TV or large screen while cooking. They need legible content, predictable focus, and complete keyboard/remote control without relying on touch or a pointer.

### Workshop attendee

An engineer or product practitioner observing the software factory. They need a transformation with obvious independent workstreams, objective acceptance criteria, and visible end-to-end value.

## Brand direction

### Product name and promise

- **Name:** TableStory
- **Tagline:** “Good food, clearly told.”
- **Personality:** warm, capable, calm, modern, and unpretentious
- **Voice:** concise and encouraging; avoid luxury restaurant language and cooking jargon where plain language works

### Visual system

- Warm cream (`#FFF8ED`) for primary page surfaces
- Tomato red (`#C9472D`) for the primary action and active states
- Herb green (`#3F6B4F`) for saved states and supporting accents
- Charcoal (`#26231F`) for primary text
- Golden yellow (`#E9B44C`) for highlights
- Cards use generous spacing, rounded corners, strong type hierarchy, and food-inspired color artwork generated with CSS; external image hosting is not required
- Mobile and TV layouts must share one recognizable brand, while TV mode may increase sizing, spacing, and focus contrast

### Required terminology

| Pocket Cinema concept | TableStory replacement |
| --- | --- |
| Movie / film / title | Recipe / dish |
| Catalog | Recipe collection |
| Genre | Category or dietary tag |
| Runtime | Total time |
| Rating | Difficulty |
| Synopsis | Description |
| Watchlist | My Cookbook |
| Poster | Recipe artwork |
| “Trending now” | “Popular this week” |

“Pocket Cinema,” “PC,” “movie,” “film,” “cinema,” “watchlist,” “poster,” “runtime,” “rating,” and “genre” must not appear in customer-visible HTML, accessible labels, empty states, page metadata, public JSON field names, or newly named source symbols representing recipe concepts. Historical Git data and the PRD itself are excluded from this terminology check.

## Scope

### In scope

- Replace the Pocket Cinema identity with the TableStory name, tagline, logo mark, colors, typography treatment, copy, and food-oriented visual language.
- Replace the film catalog with at least 12 realistic sample recipes covering breakfast, lunch, dinner, dessert, vegetarian, vegan, and quick-meal use cases.
- Replace the movie data model with an explicit recipe model.
- Provide recipe browse, search, detail, and save/remove behavior.
- Rename public URLs and JSON APIs to recipe-domain language.
- Rename customer-facing “watchlist” behavior to **My Cookbook**.
- Provide curated browse rails in TV mode.
- Preserve and adapt keyboard/remote navigation for browse and detail experiences.
- Update automated tests and documentation required to run and verify the application.

### Out of scope

- User accounts, authentication, or cross-device synchronization
- A database or persistent storage; saved recipes may remain in application memory and reset when the server restarts
- Creating, editing, rating, reviewing, or sharing recipes
- Shopping lists, pantry inventory, nutrition calculations, meal planning, video playback, timers, or voice control
- Live data from third-party recipe services
- Production deployment, analytics, payments, advertisements, or localization
- Photorealistic food photography or externally hosted media
- Backward compatibility for old `/movie/*` and `/api/movies*` URLs

## Recipe content model

Each recipe must use recipe-specific field names and contain:

- `id`: stable URL-safe identifier
- `title`: dish name
- `description`: one or two sentence summary
- `category`: one primary value such as Breakfast, Lunch, Dinner, or Dessert
- `dietary_tags`: zero or more values such as Vegetarian, Vegan, or Gluten-Free
- `prep_minutes`: positive integer
- `cook_minutes`: non-negative integer
- `difficulty`: exactly Easy, Medium, or Confident Cook
- `servings`: positive integer
- `ingredients`: non-empty ordered list of display-ready ingredient strings
- `steps`: at least three ordered instruction strings
- `colors`: two valid CSS colors used for recipe artwork
- `featured`: Boolean used to select recipes for prominent discovery

At least:

- 12 recipes are present.
- 3 recipes are vegetarian.
- 2 recipes are vegan.
- 3 recipes take 30 total minutes or less.
- 2 recipes are desserts.
- Every recipe has unique content, non-empty ingredients, and at least three steps.

## Functional requirements

### 1. Global product identity

1. Every page title, heading, navigation label, accessible name, button label, empty state, and error returned by a supported endpoint uses TableStory and recipe-domain language.
2. The header displays a TableStory brand mark and links to the browse page.
3. The home page introduces the product with the tagline “Good food, clearly told.” and a short sentence about finding recipes for everyday cooking.
4. The visual system follows the approved brand palette and remains readable in mobile and TV layouts.
5. There is no customer-visible Pocket Cinema or movie terminology in either mode.

### 2. Browse recipes

1. The default mobile home page displays all recipes as cards.
2. Each card shows the recipe title, total time (`prep_minutes + cook_minutes`), difficulty, and at least one category or dietary label.
3. Each card links to its recipe detail page at `/recipe/<recipe_id>`.
4. Each card provides a clearly labelled control to add or remove that recipe from My Cookbook.
5. The page displays the number of matching recipes and a recipe-specific empty state when no cards match.
6. Card artwork is visually varied and contains a meaningful dish initial or title treatment without depending on a network image.

### 3. Search and filtering

1. Search matches case-insensitively across recipe title, description, category, dietary tags, and ingredient text.
2. Results update on the browse page as the user types, without a full-page reload.
3. Clearing the query restores all recipes.
4. A query with no matches shows: “No recipes found. Try another ingredient or dish.”
5. The public collection endpoint accepts the same `q` behavior so server and client search semantics agree.

### 4. Recipe detail

1. `/recipe/<recipe_id>` shows the title, description, category, dietary tags, prep time, cook time, total time, difficulty, and servings.
2. Ingredients are presented as a readable list in their stored order.
3. Method steps are numbered and presented in their stored order.
4. The page includes a control to add or remove the recipe from My Cookbook and communicates the current state in its label.
5. A browse/back action returns to the correct mobile or TV version of the home page.
6. An unknown recipe ID returns HTTP 404.

### 5. My Cookbook

1. `POST /api/cookbook` with JSON `{ "id": "<recipe_id>" }` saves a valid recipe and returns HTTP 201.
2. Saving an unknown recipe returns HTTP 400 with a recipe-specific error.
3. `GET /api/cookbook` returns the complete saved recipe objects.
4. `DELETE /api/cookbook/<recipe_id>` removes a saved recipe and succeeds even if it was already absent.
5. Browse and detail controls visually and accessibly distinguish saved from unsaved recipes.
6. The “My Cookbook” TV rail reflects the saved collection after it is refreshed.

### 6. Recipe APIs

The supported public API is:

- `GET /api/recipes` — return all recipes, optionally filtered by `q`
- `GET /api/recipes/<recipe_id>` — return one recipe or HTTP 404 with `{ "error": "Recipe not found" }`
- `GET /api/cookbook` — return saved recipes
- `POST /api/cookbook` — save a recipe
- `DELETE /api/cookbook/<recipe_id>` — remove a saved recipe
- `GET /api/rails` — return named recipe groups and recipe IDs

Responses must use `recipe_ids`, not `movie_ids`. Old movie and watchlist endpoints are not part of the supported product and should be removed.

### 7. TV browse experience

1. TV mode remains available through `?mode=tv` and recognized TV user-agent hints.
2. The TV home page displays horizontal rails named:
   - Popular this week
   - Ready in 30 minutes
   - Vegetarian favourites
   - My Cookbook
3. Every non-cookbook rail contains at least two recipes from the sample data.
4. Arrow Left and Arrow Right move focus between recipe cards in a rail.
5. Arrow Up and Arrow Down move focus between rails while choosing the nearest sensible card position.
6. Enter opens the focused recipe and retains TV mode in the destination URL.
7. The focused element always has a high-contrast visible focus treatment.
8. Focus movement does not cause the selected card to remain off-screen.

### 8. TV recipe detail experience

1. Text and controls are legible from a typical television viewing distance at a 1920×1080 viewport.
2. The user can reach the back action and My Cookbook action with Arrow Up and Arrow Down.
3. Enter activates the focused action.
4. Escape or Backspace returns to the TV browse page.
5. Ingredients and steps remain available on the page; the layout may scroll, but no pointer interaction is required to reach the primary actions.

### 9. Responsive and accessible behavior

1. Supported mobile content is usable at a viewport width of 375 CSS pixels without horizontal page scrolling.
2. TV content is usable at 1920×1080 without clipped navigation controls.
3. All interactive controls have accessible names that describe recipe actions.
4. Keyboard focus is visible and follows a predictable order.
5. Text and essential UI states meet WCAG AA color contrast targets.
6. Search results and save-state changes are conveyed without relying only on color.

### 10. Documentation and verification

1. The application README identifies the product as TableStory and explains how to install dependencies, run the server, open mobile mode, and open TV mode.
2. Existing automated tests are migrated from movie terminology to recipe terminology.
3. Tests cover recipe data loading, collection search, one-recipe lookup, cookbook add/remove behavior, rails, missing recipes, TV-mode detection, TV navigation, and TV detail actions.
4. No test may pass solely by keeping deprecated movie endpoints or film-specific fixtures alive.

## Non-functional constraints

- Continue using the existing Python, Flask, HTML, CSS, and vanilla JavaScript stack.
- Do not add a frontend framework, database, build service, or external runtime dependency.
- The app must run locally with the repository's documented commands.
- The experience must work without network access after dependencies are installed.
- Preserve the existing factory and planner behavior; changes are confined to the demo application and its application documentation/tests.
- Keep data deterministic so all agents and reviewers see the same recipes.
- Prefer semantic HTML and small, testable JavaScript modules.
- Never expose secrets or require an API key to run the recipe application.

## Success measures

For the workshop demonstration, success is measured by observable completion rather than production analytics:

- A first-time reviewer identifies the product as a recipe app from the initial viewport without explanation.
- A reviewer can find a recipe by ingredient, open it, read ingredients and steps, save it, and see it in My Cookbook.
- The same browse-to-detail journey can be completed using only arrow keys, Enter, and Escape/Backspace in TV mode.
- All supported page copy, source-domain symbols, routes, API payloads, fixtures, and tests use recipe terminology.
- All automated checks pass from a clean checkout.

## Definition of done

The rebrand is complete when a human reviewer can perform all of the following:

1. Start the Flask app using the documented command.
2. Open `/` at mobile size and see the TableStory brand, recipe cards, and recipe-specific navigation.
3. Search for an ingredient known to appear in the sample data and receive only relevant results.
4. Open a recipe and verify its metadata, ingredients, and ordered cooking steps.
5. Add and remove the recipe from My Cookbook and observe an accurate accessible state.
6. Open `/?mode=tv`, navigate at least two rails with arrow keys, and open a recipe with Enter.
7. Use Arrow Up/Down on the TV detail page and return using Escape or Backspace.
8. Request every supported API and confirm recipe-specific routes, field names, responses, and errors.
9. Search rendered application files and public source symbols and find no unsupported cinema-domain terms listed in the terminology requirement.
10. Run the Python and JavaScript test suites with no failures.

## Delivery guidance for the planning agent

- Produce small, independently reviewable tickets with objective acceptance criteria.
- Separate work that can safely proceed in parallel, such as recipe data/API migration, brand styling, client interactions, TV browse behavior, TV detail behavior, and automated verification.
- Express real dependencies explicitly. In particular, user-interface work that consumes the recipe model should depend on the agreed recipe data/API contract.
- Include integration checks that catch partial rebrands, such as recipe pages still calling movie endpoints or tests retaining watchlist semantics.
- Do not create tickets for out-of-scope production capabilities.

## Open questions

None. Product name, terminology, palette, data requirements, routes, API behavior, supported devices, persistence model, and exclusions are approved for this workshop release.
