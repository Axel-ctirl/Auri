import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <p className="text-4xl" aria-hidden>
        🍞
      </p>
      <h1 className="text-lg font-semibold text-ink-100">That page is not part of Bread</h1>
      <p className="max-w-sm text-sm text-ink-400">
        The address does not match any of Bread's pages. Nothing is broken.
      </p>
      <Link to="/" className="btn-primary">
        Back to chat
      </Link>
    </div>
  );
}
