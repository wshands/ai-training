/* eslint-disable testing-library/no-unnecessary-act */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import JobStatusBadge from './JobStatusBadge';
import { JobState } from '../constants/jobStates';

it('renders the job status text', () => {
  const container = document.createElement('div');
  const root = createRoot(container);

  act(() => {
    root.render(<JobStatusBadge status={JobState.RUNNING} />);
  });

  expect(container.textContent).toContain(JobState.RUNNING);
  act(() => {
    root.unmount();
  });
});
