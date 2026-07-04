document.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
  const tabs = Array.from(document.querySelectorAll(".tab"));
  const active = tabs.findIndex((tab) => tab.classList.contains("active"));
  const next = event.key === "ArrowRight" ? (active + 1) % tabs.length : (active - 1 + tabs.length) % tabs.length;
  tabs[next].focus();
});

