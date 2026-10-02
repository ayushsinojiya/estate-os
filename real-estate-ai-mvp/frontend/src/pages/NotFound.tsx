import { Link } from "react-router-dom";
import { Building2 } from "../components/icons";
import { usePageMetadata } from "../hooks/usePageMetadata";

export function NotFound() {
  usePageMetadata("Page not found", "The requested EstraOS page could not be found.");
  return (
    <div className="not-found-page">
      <Link to="/dashboard" className="brand">
        <span className="brand-icon"><Building2 size={23} /></span>
        <span>Estra<span className="font-normal">OS</span></span>
      </Link>
      <main>
        <span className="eyebrow">404 · PAGE NOT FOUND</span>
        <h1>Page not found</h1>
        <p>The page may have moved, or the link may be incorrect.</p>
        <Link className="btn-primary" to="/dashboard">Go to dashboard</Link>
      </main>
    </div>
  );
}
