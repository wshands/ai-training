import React from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuth, useUser } from '@clerk/clerk-react';
import { useAppAuth } from '../context/AppAuthContext';
import { hasMinRole } from '../utils/roles';

const NavItem = ({ to, children }) => (
  <NavLink
    to={to}
    className={({ isActive }) =>
      `px-3 py-1 rounded-md text-sm font-medium ${
        isActive
          ? 'bg-sky-500 text-white'
          : 'text-slate-200 hover:bg-slate-700 hover:text-white'
      }`
    }
  >
    {children}
  </NavLink>
);

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isSignedIn, signOut } = useAuth();
  const { user } = useUser();
  const { role, loading: roleLoading } = useAppAuth();
  const canSubmit = hasMinRole(role, 'operator');
  const isAdmin = hasMinRole(role, 'admin');
  const isAuthRoute =
    location.pathname.startsWith('/login') || location.pathname.startsWith('/register');
  const showAppLinks = isSignedIn && !isAuthRoute;
  const showAuthLinks = !isSignedIn;

  const onLogout = async () => {
    await signOut({ redirectUrl: '/' });
    navigate('/');
  };

  return (
    <header className="bg-slate-900 border-b border-slate-800">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link to="/" className="font-semibold text-sky-400">
          AiTrainOps
        </Link>
        <nav className="flex gap-2 items-center">
          {showAppLinks && (
            <>
              <NavItem to="/app">Jobs</NavItem>
              {canSubmit ? (
                <NavItem to="/jobs/new">New Job</NavItem>
              ) : (
                <span
                  className="px-3 py-1 rounded-md text-sm font-medium text-slate-500 cursor-not-allowed"
                  title={roleLoading ? 'Loading permissions…' : 'Read-only role'}
                >
                  New Job
                </span>
              )}
              {isAdmin && <NavItem to="/admin/tokens">Admin</NavItem>}
            </>
          )}
          {showAuthLinks && (
            <>
              {isAuthRoute ? (
                <NavItem to={location.pathname.startsWith('/login') ? '/register' : '/login'}>
                  {location.pathname.startsWith('/login') ? 'Request access' : 'Sign in'}
                </NavItem>
              ) : (
                <>
                  <NavItem to="/login">Sign in</NavItem>
                  <NavItem to="/register">Request access</NavItem>
                </>
              )}
            </>
          )}
          {isSignedIn && (
            <span className="text-xs text-slate-300">
              {user?.primaryEmailAddress?.emailAddress ||
                user?.username ||
                user?.id ||
                'Signed in'}
            </span>
          )}
          {isSignedIn && (
            <button
              type="button"
              onClick={onLogout}
              className="px-3 py-1 rounded-md text-sm font-medium text-slate-200 hover:bg-slate-700 hover:text-white"
            >
              Sign out
            </button>
          )}
        </nav>
      </div>
    </header>
  );
};

export default Navbar;
