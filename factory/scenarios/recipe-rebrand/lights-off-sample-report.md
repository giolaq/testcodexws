# Lights-off control — deterministic discussion fixture

> This is a workshop fixture, not an empirical model benchmark. It represents
> a plausible one-shot outcome when no live model credentials are available.

## Simulated result

The direct agent completed a recognizable TableStory mobile experience and
reported its existing tests as green. Review found that it made several
reasonable but unreviewed assumptions:

- It retained deprecated movie API aliases for compatibility even though the
  PRD explicitly removed backward compatibility from scope.
- It reused one broad application module instead of defining clear recipe,
  delivery, mobile, and TV boundaries.
- It interpreted “TV navigation works” as browse-card movement and did not test
  every detail action or mode-preserving return path.
- It updated visible headings but missed cinema terminology in metadata,
  accessible labels, one empty state, and test fixture names.
- It added tests after implementation, primarily around the code structure it
  had already chosen.

## Simulated verification

| Evidence | Result | Review note |
| --- | --- | --- |
| Recognizable TableStory mobile page | Pass | Brand and recipe cards are visible. |
| Recipe data and search | Pass | Ingredient search works. |
| My Cookbook journey | Pass | In-memory add and remove work. |
| Complete TV key journey | Partial | Browse works; detail return loses TV mode. |
| Forbidden terminology scan | Fail | Metadata, labels, and fixtures contain old terms. |
| Documentation from a clean checkout | Partial | Mobile startup is documented; TV verification is missing. |
| Requirement-to-evidence traceability | Missing | Reviewer must reconstruct it from code and tests. |

## Comparison scorecard

Fill this after the factory run. Use counts or short observations rather than
“better” and “worse.”

| Measure | Lights-off control | Factory |
| --- | --- | --- |
| Elapsed execution time | | |
| Requirements fully evidenced | | |
| Automated gates passing | | |
| Unresolved assumptions discovered in review | | |
| Customer-facing terminology defects | | |
| Files in the largest review unit | | |
| Human review/rework time | | |
| Safe parallel work visible in advance | No | |
| Requirement-to-QA traceability | No | |
| Intermediate decisions independently reviewable | No | |

## Discussion

The control is not automatically lower quality. Its disadvantage is that
product interpretation, architecture, program design, test strategy, and slice
ownership become visible mostly through one final diff. Ask which problems
would have been cheaper to resolve before implementation and which factory
controls added useful evidence rather than ceremony.
