const questionForm = document.getElementById("question-form");
const askButton = document.getElementById("ask-button");
const questionStatus = document.getElementById("question-status");

questionForm.addEventListener("submit", () => {
  questionForm.setAttribute("aria-busy", "true");
  askButton.disabled = true;
  askButton.textContent = "Generating…";
  questionStatus.textContent = "Searching permitted documents and generating an answer…";
});
