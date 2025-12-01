import JobList from "../components/JobList";

export default function Home() {
  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>AI Platform Job Dashboard</h1>
      <JobList />
    </main>
  );
}
