# React + TypeScript Project

Components, state, data fetching and the patterns that keep a UI predictable.

Triggers: react, jsx, tsx, hook, usestate, useeffect, component, vite, next.js

You are helping with a **React + TypeScript** project.

Assume function components and hooks. Class components only come up in legacy
code, and if that is what the user has, say so before rewriting.

Conventions to follow:

- Type props with an explicit interface. Avoid `React.FC`; it adds an implicit
  `children` that is usually wrong.
- Derive state instead of duplicating it. If a value can be computed from props
  or other state, compute it during render rather than syncing it in an effect.
- `useEffect` is for synchronising with something outside React: a subscription,
  a timer, an imperative DOM API. Data fetching belongs in a query library
  (TanStack Query) that handles caching, retries and race conditions for you.
- Every list item needs a stable `key`. An array index is a bug as soon as the
  list can reorder.
- Keep components small enough to name honestly. When a component's name needs
  "and" in it, split it.
- Handle the three states every async view has: loading, error, empty. A UI that
  only handles success is not finished.
- Abort in-flight requests on unmount with an `AbortController`, or let the
  query library do it.

For styling, follow whatever the project already uses. Do not introduce a second
styling system alongside an existing one.

Accessibility is not optional: real `<button>` elements for actions, labels tied
to inputs, and focus states that survive keyboard navigation.
