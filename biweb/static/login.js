(() => {
  const form = document.getElementById("login-form");
  if (!form) return;

  const password = document.getElementById("login-password");
  const toggle = document.getElementById("toggle-password");
  const caps = document.getElementById("caps-warning");
  const submit = form.querySelector(".auth-submit");

  // Mostrar / ocultar contrasena
  toggle.addEventListener("click", () => {
    const visible = password.type === "text";
    password.type = visible ? "password" : "text";
    toggle.setAttribute("aria-pressed", String(!visible));
    toggle.setAttribute("aria-label", visible ? "Mostrar contrasena" : "Ocultar contrasena");
    toggle.classList.toggle("is-on", !visible);
    password.focus();
  });

  // Aviso de Bloq Mayus
  const checkCaps = (event) => {
    if (typeof event.getModifierState === "function") {
      caps.hidden = !event.getModifierState("CapsLock");
    }
  };
  password.addEventListener("keydown", checkCaps);
  password.addEventListener("keyup", checkCaps);
  password.addEventListener("blur", () => { caps.hidden = true; });

  // Validacion ligera y estado de carga
  form.addEventListener("submit", (event) => {
    const empty = [...form.querySelectorAll(".auth-field input[required]")].filter((input) => !input.value.trim());
    if (empty.length) {
      event.preventDefault();
      empty.forEach((input) => input.closest(".auth-field").classList.add("is-invalid"));
      empty[0].focus();
      form.classList.remove("shake");
      void form.offsetWidth;
      form.classList.add("shake");
      return;
    }
    submit.classList.add("is-loading");
    submit.disabled = true;
  });

  // Al volver con el boton "atras" el navegador puede restaurar el boton bloqueado
  window.addEventListener("pageshow", () => {
    submit.classList.remove("is-loading");
    submit.disabled = false;
  });

  form.querySelectorAll(".auth-field input").forEach((input) => {
    input.addEventListener("input", () => input.closest(".auth-field").classList.remove("is-invalid"));
  });

  // Si el login fallo, enfocar la contrasena para reintentar rapido
  if (form.classList.contains("has-error")) {
    form.classList.add("shake");
    password.focus();
  }
})();
