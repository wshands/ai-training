import { useEffect, useState } from "react";

export default function JobList() {
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    async function fetchJobs() {
      try {
        const res = await fetch("http://localhost:8000/jobs"); // placeholder
        if (res.ok) {
          const data = await res.json();
          setJobs(data.jobs || []);
        }
      } catch (e) {
        console.error(e);
      }
    }
    fetchJobs();
  }, []);

  return (
    <section style={{ marginTop: 16 }}>
      <h2>Jobs</h2>
      {jobs.length === 0 && <p>No jobs yet.</p>}
      <ul>
        {jobs.map((job) => (
          <li key={job.job_id}>
            {job.job_id} – {job.status || "UNKNOWN"}
          </li>
        ))}
      </ul>
    </section>
  );
}
