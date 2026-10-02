# Website quality audit

Source: the user's 20-item screenshot, applied to the EstraOS React workspace rather than a public marketing site. The image is a checklist of suggestions; this audit records the project-specific decision for each item.

| Item | Current state and action |
| --- | --- |
| 1. Horizontal scrolling | Check every routed workspace view at narrow and desktop widths. Keep data tables scrollable within their panels; fix page-level overflow. |
| 2. Broken links | Verify every internal navigation destination and the skip link. Replace the generic unknown-route empty state with a useful 404 page. |
| 3. Mobile menu | Already present. Verify opening, closing, focus, and small-screen layout. |
| 4. Favicon | Add a small vector EstraOS favicon and reference it from HTML. |
| 5. Page titles | Set the browser title from each page header, including login and 404. |
| 6. Meta descriptions | Keep the existing default and update it for the current route. |
| 7. Footer links | No footer links exist. Do not invent unrelated destinations. |
| 8. Custom 404 | Add an actionable unknown-route page with a link back to the dashboard. |
| 9. Copyright year | Add the current year to the workspace footer. |
| 10. Compress images | There are no bundled raster assets. Project cards show externally supplied media; load them lazily and decode asynchronously. Source-image compression belongs to the upload/media pipeline, not this UI. |
| 11. Broken buttons | Exercise the primary navigation and actions in browser tests; fix any failures found. |
| 12. Success messages | Existing toast provider covers write actions. Verify representative flows. |
| 13. Error messages | Existing error states cover requests and forms. Verify representative failures. |
| 14. Placeholder text | Form hints are functional. No lorem ipsum or unfinished page copy was found; retain helpful input prompts. |
| 15. Unused navigation | Sidebar already omits the previously hidden routes while valid pages remain addressable. Verify all displayed links. |
| 16. Mobile overflow | Audit 320, 768, 1024, and 1440 pixel layouts and fix clipped controls or page-wide overflow. |
| 17. Clickable logo | Workspace logo already links to the dashboard. Verify it; make the sign-in logo a home link. |
| 18. Clickable phone number | Link lead phone values with `tel:` wherever they are presented as contact details. |
| 19. Clickable email | Link lead, member, and profile email values with `mailto:` wherever presented as contact details. |
| 20. Mobile pages | Verify representative views, forms, tables, menus, and a detail page at narrow widths; make targeted layout fixes. |

Implementation references: [MDN viewport guidance](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport), [web.dev responsive layout guidance](https://web.dev/articles/responsive-web-design-basics), [web.dev responsive table patterns](https://web.dev/learn/design/ui-patterns/), [MDN icon metadata](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/rel), and [MDN contact links](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/address).

## Verification

- The signed-in workspace was checked in a disposable Docker stack. Every routed view was checked at 320px; login, dashboard, lead table, and a detail view were checked at 320, 768, 1024, and 1440px. None produced page-level horizontal overflow; the lead table retained its own horizontal scroll.
- The mobile menu, logo and sidebar navigation, booking dialog and date picker, 404 page, favicon response, route titles, contact links, and footer year were checked in the browser.
- A lead and note were saved in the disposable database. An incomplete site-visit booking produced a visible error message. The disposable stack and its volumes were then removed.
- Frontend: 45 tests passed; lint and production build passed. All three Compose files passed configuration validation.
