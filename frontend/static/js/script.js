async function redirectToLocalhostIfAvailable() {
    if (window.location.protocol !== "file:") return;
    try {
        const response = await fetch("http://localhost:3000/index.html", { method: "HEAD" });
        if (response.ok) {
            window.location.href = "http://localhost:3000/index.html";
        }
    } catch (err) {
        // do nothing if local server is not running
    }
}

redirectToLocalhostIfAvailable();

// smooth button animation

const buttons = document.querySelectorAll("button");

buttons.forEach(btn => {
    btn.addEventListener("mouseenter", () => {
        btn.style.transform = "translateY(-3px)";
    });

    btn.addEventListener("mouseleave", () => {
        btn.style.transform = "translateY(0)";
    });
});

// navbar shadow on scroll

window.addEventListener("scroll", () => {

    const navbar = document.querySelector(".navbar");

    if(window.scrollY > 50){
        navbar.style.boxShadow = "0 5px 20px rgba(0,0,0,.08)";
    }
    else{
        navbar.style.boxShadow = "none";
    }

});

// fade in cards

const cards = document.querySelectorAll(
".value-card,.pillar-card"
);

const observer = new IntersectionObserver(entries => {

    entries.forEach(entry => {

        if(entry.isIntersecting){

            entry.target.style.opacity = "1";
            entry.target.style.transform = "translateY(0)";

        }

    });

});

cards.forEach(card => {

    card.style.opacity = "0";
    card.style.transform = "translateY(40px)";
    card.style.transition = "all .8s ease";

    observer.observe(card);

});