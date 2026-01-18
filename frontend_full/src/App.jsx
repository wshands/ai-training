import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import NewJobWizard from './pages/NewJobWizard';
import JobDetail from './pages/JobDetail';

const App = () => (
  <div className="min-h-screen flex flex-col">
    <Navbar />
    <main className="flex-1">
      <div className="max-w-6xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs/new" element={<NewJobWizard />} />
          <Route path="/jobs/:jobId" element={<JobDetail />} />
        </Routes>
      </div>
    </main>
  </div>
);

export default App;
