/*
 * Dashboard behaviour. Vanilla, no dependencies, no network calls.
 *
 * Everything here is an enhancement: the page works with JavaScript off.
 * The `js` class on <html> is what the stylesheet keys the two differing
 * states off, and it is set as the first thing this file does so there is no
 * flash of the no-JS layout.
 *
 *   - Modify reveals the price box and a Confirm button. Without JS the box
 *     is already visible and Modify submits it directly.
 *   - Submit buttons show a spinner and go disabled, so a slow prediction
 *     cannot be double-submitted.
 *   - Load example and Reset fill the form from values the server rendered
 *     into a JSON block, so no listing data is hard-coded here.
 */

(function () {
  "use strict";

  document.documentElement.classList.add("js");

  document.addEventListener("DOMContentLoaded", function () {
    setUpModifyFlow();
    setUpLoadingStates();
    setUpFormPresets();
  });

  /* ------------------------------------------------------------ modify */

  function setUpModifyFlow() {
    var form = document.querySelector("[data-decision-form]");
    if (!form) {
      return;
    }
    var modify = form.querySelector('[value="modify"]');
    var panel = form.querySelector("[data-modify-panel]");
    var price = form.querySelector('[name="final_price"]');
    var confirm = form.querySelector("[data-confirm-modify]");
    if (!modify || !panel || !price || !confirm) {
      return;
    }

    modify.addEventListener("click", function (event) {
      if (panel.classList.contains("is-open")) {
        return; // Panel already open: let the submit through.
      }
      event.preventDefault();
      panel.classList.add("is-open");
      modify.setAttribute("aria-expanded", "true");
      price.focus();
    });

    // requestSubmit names the Modify button as the submitter, so the form
    // sends decision=modify exactly as if Modify had been clicked.
    confirm.addEventListener("click", function () {
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(modify);
      } else {
        modify.click();
      }
    });
  }

  /* ----------------------------------------------------------- loading */

  function setUpLoadingStates() {
    var forms = document.querySelectorAll("form[data-loading]");
    Array.prototype.forEach.call(forms, function (form) {
      form.addEventListener("submit", function (event) {
        var submitter = event.submitter;
        if (!submitter || submitter.disabled) {
          return;
        }
        // Re-entering the page from history must not leave a dead button, so
        // the state is applied after the navigation has been committed.
        window.setTimeout(function () {
          submitter.classList.add("is-loading");
          submitter.setAttribute("aria-busy", "true");
          submitter.disabled = true;
        }, 0);
      });
    });
  }

  /* ----------------------------------------------------------- presets */

  function setUpFormPresets() {
    var holder = document.getElementById("form-presets");
    var form = document.querySelector("[data-input-form]");
    if (!holder || !form) {
      return;
    }

    var presets;
    try {
      presets = JSON.parse(holder.textContent);
    } catch (error) {
      return; // Nothing to fill from; the form keeps its rendered values.
    }

    bindPreset(form, presets.example, "[data-load-example]");
    bindPreset(form, presets.defaults, "[data-reset-form]");
  }

  function bindPreset(form, values, selector) {
    var button = document.querySelector(selector);
    if (!button || !values) {
      return;
    }
    button.addEventListener("click", function () {
      applyValues(form, values);
      announce(form, button.getAttribute("data-announce") || "Form updated");
    });
  }

  function applyValues(form, values) {
    Object.keys(values).forEach(function (name) {
      var field = form.elements.namedItem(name);
      if (!field) {
        return;
      }
      var value = values[name];
      field.value = value === null ? "" : String(value);
      // Clear any server-rendered error styling on a field we just replaced.
      var wrapper = field.closest(".field");
      if (wrapper) {
        wrapper.classList.remove("has-error");
      }
    });
  }

  /*
   * Fills a live region so a screen reader is told the form changed. Without
   * this, pressing Load example moves 25 values silently.
   */
  function announce(form, message) {
    var region = document.getElementById("form-status");
    if (region) {
      region.textContent = message;
    }
  }
})();
