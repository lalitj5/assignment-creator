const form = document.getElementById("assignment-form");
const submitBtn = document.getElementById("submit-btn");
const spinner = document.getElementById("spinner");
const errorMsg = document.getElementById("error-msg");
const result = document.getElementById("result");
const pdfPreview = document.getElementById("pdf-preview");
const downloadLink = document.getElementById("download-link");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  // Reset UI state
  errorMsg.textContent = "";
  errorMsg.classList.add("hidden");
  result.classList.add("hidden");
  spinner.classList.remove("hidden");
  submitBtn.disabled = true;

  const formData = new FormData(form);

  try {
    const response = await fetch("http://localhost:8000/generate", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let detail = `Server error ${response.status}`;
      try {
        const json = await response.json();
        if (json.detail) detail = json.detail;
      } catch (_) {}
      throw new Error(detail);
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);

    pdfPreview.src = objectUrl;
    downloadLink.href = objectUrl;
    result.classList.remove("hidden");
  } catch (err) {
    errorMsg.textContent = err.message || "An unexpected error occurred.";
    errorMsg.classList.remove("hidden");
  } finally {
    spinner.classList.add("hidden");
    submitBtn.disabled = false;
  }
});
