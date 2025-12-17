import React from 'react';
import { Link, NavLink } from 'react-router-dom';

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

const Navbar = () => (
  <header className="bg-slate-900 border-b border-slate-800">
    <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
      <Link to="/" className="font-semibold text-sky-400">
        AI Training Control Plane
      </Link>
      <nav className="flex gap-2">
        <NavItem to="/">Jobs</NavItem>
        <NavItem to="/jobs/new">New Job</NavItem>
        <NavItem to="/deployments">Deployments</NavItem>
      </nav>
    </div>
  </header>
);

export default Navbar;
