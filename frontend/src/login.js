document.getElementById("loginForm").addEventListener("submit", function(e) {
    e.preventDefault();

    // Later you can validate credentials here

    window.location.href = "dashboard.html";
});