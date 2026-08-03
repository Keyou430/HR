/**
 * App entry point — sets up window.__auth before the inline script runs.
 *
 * Vite serves this as a module; it executes after DOM parse but before
 * DOMContentLoaded.  The inline <script> further down index.html reads
 * window.__auth once it's ready.
 */

// Import authContext to trigger the side-effect that creates window.__auth
import './auth/authContext';

// Import permissions module for side-effect (exposes helpers)
import { hasPermission, hasRole, isAuthenticated, PERM, ROLE } from './auth/permissions';

// Expose permissions globally for vanilla JS access in index.html
if (typeof window !== "undefined") {
  const win = window as unknown as Record<string, unknown>;
  win.__perm = { hasPermission, hasRole, isAuthenticated, PERM, ROLE };
}

// Re-export for consumers
export { default as auth } from './auth/authContext';
export { hasPermission, hasRole, isAuthenticated, PERM, ROLE } from './auth/permissions';
