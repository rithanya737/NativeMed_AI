// ---------- Activity Overview (Line Chart) ----------
const activityLabels = window.activityLabels || [];
const activityQueries = window.activityQueries || [];
const activityContributions = window.activityContributions || [];

const categoryLabels = window.categoryLabels || [];
const categoryCounts = window.categoryCounts || [];

const monthLabels = window.monthLabels || [];
const monthContributionCounts = window.monthContributionCounts || [];

let activityChartInstance, pieChartInstance, contributionChartInstance;

function renderCharts() {
  const activityCtx = document.getElementById("activityChart");
  if (activityCtx) {
    if (activityChartInstance) activityChartInstance.destroy();
    activityChartInstance = new Chart(activityCtx, {
      type: "line",
      data: {
        labels: activityLabels,
        datasets: [
          {
            label: "AI Queries",
            data: activityQueries,
            borderColor: "#2E7D32",
            backgroundColor: "rgba(46,125,50,0.15)",
            fill: true,
            tension: 0.4
          },
          {
            label: "Contributions",
            data: activityContributions,
            borderColor: "#66BB6A",
            backgroundColor: "rgba(102,187,106,0.15)",
            fill: true,
            tension: 0.4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top" } }
      }
    });
  }

  const pieCtx = document.getElementById("pieChart");
  if (pieCtx) {
    if (pieChartInstance) pieChartInstance.destroy();
    pieChartInstance = new Chart(pieCtx, {
      type: "doughnut",
      data: {
        labels: categoryLabels,
        datasets: [{
          data: categoryCounts,
          backgroundColor: ["#2E7D32","#43A047","#66BB6A","#81C784","#A5D6A7","#C8E6C9"]
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { boxWidth: 12, font: { size: 11 } } } }
      }
    });
  }

  const contributionCtx = document.getElementById("contributionChart");
  if (contributionCtx) {
    if (contributionChartInstance) contributionChartInstance.destroy();
    contributionChartInstance = new Chart(contributionCtx, {
      type: "bar",
      data: {
        labels: monthLabels,
        datasets: [{ label: "Contributions", data: monthContributionCounts, backgroundColor: "#43A047" }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } }
      }
    });
  }
}

renderCharts();

// ---------- Live refresh: pull fresh DB numbers every 60s without a full reload ----------
async function refreshDashboard() {
  try {
    const res = await fetch("/api/dashboard-data");
    if (res.status === 401) {
      window.location.href = "/signin";
      return;
    }
    if (!res.ok) return;

    const data = await res.json();

    activityLabels.length = 0; activityLabels.push(...data.activity_labels);
    activityQueries.length = 0; activityQueries.push(...data.activity_queries);
    activityContributions.length = 0; activityContributions.push(...data.activity_contributions);
    categoryLabels.length = 0; categoryLabels.push(...data.category_labels);
    categoryCounts.length = 0; categoryCounts.push(...data.category_counts);
    monthLabels.length = 0; monthLabels.push(...data.month_labels);
    monthContributionCounts.length = 0; monthContributionCounts.push(...data.month_contribution_counts);

    renderCharts();

    const tbody = document.getElementById("recentActivityBody");
    if (tbody && data.recent) {
      tbody.innerHTML = data.recent.length
        ? data.recent.map(r => `<tr><td>${r.type}</td><td>${r.detail}</td><td>${r.status}</td><td>${r.date}</td></tr>`).join("")
        : `<tr><td colspan="4">No activity yet — try identifying a plant or asking the assistant a question.</td></tr>`;
    }
  } catch (err) {
    console.error("Dashboard refresh failed:", err);
  }
}

setInterval(refreshDashboard, 60000);

// ---------- Logout ----------
const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", () => {
    localStorage.removeItem("loggedInUser");
    window.location.href = "/logout";
  });
}