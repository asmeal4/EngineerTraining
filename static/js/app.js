(function () {
  function debounce(fn, ms) {
    var timer;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(self, args);
      }, ms);
    };
  }

  var AUTO_FILTER_FOCUS_KEY = "autoFilterFocus";

  function saveAutoFilterFocus(el) {
    if (!el || !el.name) return;
    var state = { name: el.name, path: location.pathname };
    if (typeof el.selectionStart === "number") {
      state.start = el.selectionStart;
      state.end = el.selectionEnd;
    }
    try {
      sessionStorage.setItem(AUTO_FILTER_FOCUS_KEY, JSON.stringify(state));
    } catch (e) {}
  }

  function restoreAutoFilterFocus() {
    var raw;
    try {
      raw = sessionStorage.getItem(AUTO_FILTER_FOCUS_KEY);
      sessionStorage.removeItem(AUTO_FILTER_FOCUS_KEY);
    } catch (e) {
      return;
    }
    if (!raw) return;
    var state;
    try {
      state = JSON.parse(raw);
    } catch (e) {
      return;
    }
    if (!state || state.path !== location.pathname || !state.name) return;
    var el = document.querySelector(
      'form[data-auto-filter] [name="' + state.name + '"]'
    );
    if (!el) return;
    el.focus();
    if (
      typeof el.setSelectionRange === "function" &&
      typeof state.start === "number" &&
      typeof state.end === "number"
    ) {
      try {
        el.setSelectionRange(state.start, state.end);
      } catch (e) {}
    }
  }

  function initAutoFilters() {
    restoreAutoFilterFocus();
    document.querySelectorAll("form[data-auto-filter]").forEach(function (form) {
      var lastQuery = null;
      var submitForm = function (force, focusEl) {
        var searchInput = form.querySelector('input[type="search"]');
        var currentQuery = searchInput ? searchInput.value : "";
        if (!force && searchInput && currentQuery === lastQuery) return;
        lastQuery = currentQuery;
        var active = focusEl || document.activeElement;
        if (
          active &&
          form.contains(active) &&
          (active.matches('input[type="search"]') || active.tagName === "SELECT")
        ) {
          saveAutoFilterFocus(active);
        } else if (searchInput) {
          saveAutoFilterFocus(searchInput);
        }
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      };
      var debouncedSubmit = debounce(function () {
        submitForm(false);
      }, 900);

      form.querySelectorAll('input[type="search"]').forEach(function (input) {
        lastQuery = input.value;
        input.addEventListener("input", debouncedSubmit);
        input.addEventListener("keydown", function (e) {
          if (e.key === "Enter") {
            e.preventDefault();
            submitForm(true, input);
          }
        });
      });
      form.querySelectorAll("select").forEach(function (select) {
        select.addEventListener("change", function () {
          submitForm(true, select);
        });
      });
      form.querySelectorAll('input[type="date"]').forEach(function (input) {
        input.addEventListener("change", function () {
          submitForm(true, input);
        });
      });
    });
  }

  function updatePickerSummary(picker) {
    var summary = picker.querySelector(".system-multi-summary");
    var placeholder = picker.getAttribute("data-placeholder") || "اختر";
    var checked = picker.querySelectorAll('input[type="checkbox"]:checked');
    if (!summary) return;
    if (!checked.length) {
      summary.textContent = placeholder;
      summary.classList.add("is-placeholder");
    } else if (checked.length === 1) {
      var label =
        checked[0].getAttribute("data-label") ||
        (checked[0].nextElementSibling
          ? checked[0].nextElementSibling.textContent
          : "1");
      summary.textContent = label;
      summary.classList.remove("is-placeholder");
    } else {
      summary.textContent = checked.length + " عناصر محددة";
      summary.classList.remove("is-placeholder");
    }

    var targetId = picker.getAttribute("data-summary-target");
    if (!targetId) return;
    var list = document.getElementById(targetId);
    if (!list) return;
    list.innerHTML = "";
    if (!checked.length) {
      var empty = document.createElement("li");
      empty.className = "empty compact";
      empty.setAttribute("data-empty", "");
      if (targetId.indexOf("work") >= 0) {
        empty.textContent = "لم يُختر أي نوع عمل";
      } else if (targetId.indexOf("problem") >= 0) {
        empty.textContent = "لم يُختر أي مشكلة";
      } else {
        empty.textContent = "لم يُختر أي نظام";
      }
      list.appendChild(empty);
      return;
    }
    checked.forEach(function (cb) {
      var li = document.createElement("li");
      var label =
        cb.getAttribute("data-label") ||
        (cb.nextElementSibling ? cb.nextElementSibling.textContent : cb.value);
      li.innerHTML = "<strong>" + label + "</strong>";
      list.appendChild(li);
    });
  }

  function filterPickerOptions(picker) {
    var search = picker.querySelector("[data-multi-picker-search]");
    var options = picker.querySelectorAll("[data-multi-picker-option]");
    var noMatch = picker.querySelector("[data-multi-picker-no-match]");
    if (!search || !options.length) return;
    var q = (search.value || "").trim().toLowerCase();
    var visible = 0;
    options.forEach(function (opt) {
      var text = (
        opt.getAttribute("data-search-text") ||
        opt.textContent ||
        ""
      ).toLowerCase();
      var show = !q || text.indexOf(q) !== -1;
      if (show) {
        opt.removeAttribute("hidden");
        visible += 1;
      } else {
        opt.setAttribute("hidden", "");
      }
    });
    if (noMatch) {
      if (visible === 0) noMatch.removeAttribute("hidden");
      else noMatch.setAttribute("hidden", "");
    }
  }

  function resetPickerSearch(picker) {
    var search = picker.querySelector("[data-multi-picker-search]");
    if (search) search.value = "";
    filterPickerOptions(picker);
  }

  function closeAllMultiPickers() {
    document.querySelectorAll("[data-system-multi-picker]").forEach(function (p) {
      p.classList.remove("is-open");
      var pan = p.querySelector(".system-multi-panel");
      var trg = p.querySelector(".system-multi-trigger");
      if (pan) pan.setAttribute("hidden", "");
      if (trg) trg.setAttribute("aria-expanded", "false");
      resetPickerSearch(p);
    });
  }

  function initMultiPickers() {
    document.querySelectorAll("[data-system-multi-picker]").forEach(function (picker) {
      var trigger = picker.querySelector(".system-multi-trigger");
      var panel = picker.querySelector(".system-multi-panel");
      var search = picker.querySelector("[data-multi-picker-search]");
      if (!trigger || !panel) return;

      trigger.addEventListener("click", function (e) {
        e.preventDefault();
        var open = panel.hasAttribute("hidden");
        closeAllMultiPickers();
        if (open) {
          panel.removeAttribute("hidden");
          picker.classList.add("is-open");
          trigger.setAttribute("aria-expanded", "true");
          if (search) {
            setTimeout(function () {
              search.focus();
            }, 0);
          }
        }
      });

      if (search) {
        search.addEventListener("input", function () {
          filterPickerOptions(picker);
        });
        search.addEventListener("keydown", function (e) {
          if (e.key === "Escape") {
            e.preventDefault();
            closeAllMultiPickers();
            trigger.focus();
          }
          e.stopPropagation();
        });
        search.addEventListener("click", function (e) {
          e.stopPropagation();
        });
      }

      picker.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
        cb.addEventListener("change", function () {
          updatePickerSummary(picker);
        });
      });
      updatePickerSummary(picker);
    });

    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-system-multi-picker]")) return;
      closeAllMultiPickers();
    });
  }

  function initFloatWindows() {
    var checkbox = document.querySelector("[data-toggle-explanation]");
    var tools = document.getElementById("explanation-tools");
    if (checkbox && tools) {
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) {
          tools.removeAttribute("hidden");
        } else {
          tools.setAttribute("hidden", "");
          document.querySelectorAll(".float-window").forEach(function (w) {
            w.setAttribute("hidden", "");
          });
        }
      });
    }

    document.querySelectorAll("[data-open-float]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-open-float");
        var win = document.getElementById(id);
        if (win) win.removeAttribute("hidden");
      });
    });

    document.querySelectorAll("[data-close-float]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-close-float");
        var win = document.getElementById(id);
        if (win) win.setAttribute("hidden", "");
      });
    });

    // Sync floating editors into form fields before submit
    var form = document.querySelector('form[enctype="multipart/form-data"]');
    var explanationEditor = document.getElementById("explanation-editor");
    var explanationField = document.getElementById("explanation-field");
    var imageEditor = document.getElementById("image-editor");
    var imageField = document.getElementById("image-field");
    var clearCheck = document.getElementById("clear-image-check");
    var clearField = document.getElementById("clear-image-field");

    if (explanationEditor && explanationField) {
      explanationEditor.addEventListener("input", function () {
        explanationField.value = explanationEditor.value;
      });
    }

    if (imageEditor && imageField) {
      imageEditor.addEventListener("change", function () {
        if (imageEditor.files && imageEditor.files[0]) {
          var dt = new DataTransfer();
          dt.items.add(imageEditor.files[0]);
          imageField.files = dt.files;
          if (clearField) clearField.value = "0";
          if (clearCheck) clearCheck.checked = false;
        }
      });
    }

    if (clearCheck && clearField) {
      clearCheck.addEventListener("change", function () {
        clearField.value = clearCheck.checked ? "1" : "0";
      });
    }

    if (form) {
      form.addEventListener("submit", function () {
        if (explanationEditor && explanationField) {
          explanationField.value = explanationEditor.value;
        }
        if (clearCheck && clearField) {
          clearField.value = clearCheck.checked ? "1" : "0";
        }
      });
    }

    // Simple drag for float windows
    document.querySelectorAll(".float-window").forEach(function (win) {
      var head = win.querySelector(".float-window-head");
      if (!head) return;
      var dragging = false;
      var startX = 0;
      var startY = 0;
      var origLeft = 0;
      var origTop = 0;
      head.addEventListener("mousedown", function (e) {
        if (e.target.closest("button")) return;
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        var rect = win.getBoundingClientRect();
        origLeft = rect.left;
        origTop = rect.top;
        win.style.right = "auto";
        win.style.left = origLeft + "px";
        win.style.top = origTop + "px";
        e.preventDefault();
      });
      document.addEventListener("mousemove", function (e) {
        if (!dragging) return;
        win.style.left = origLeft + (e.clientX - startX) + "px";
        win.style.top = origTop + (e.clientY - startY) + "px";
      });
      document.addEventListener("mouseup", function () {
        dragging = false;
      });
    });
  }

  function initWorkTypeToggle() {
    document.querySelectorAll("[data-work-type-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var packageId = btn.getAttribute("data-package-id");
        var workId = btn.getAttribute("data-work-id");
        var detailRow = document.querySelector(
          '[data-package-detail="' + packageId + '"]'
        );
        if (!detailRow) return;

        var alreadyOpen =
          btn.classList.contains("is-open") &&
          !detailRow.hasAttribute("hidden");

        // Close all work toggles for this package
        document
          .querySelectorAll(
            '[data-work-type-toggle][data-package-id="' + packageId + '"]'
          )
          .forEach(function (b) {
            b.classList.remove("is-open");
            b.setAttribute("aria-expanded", "false");
          });
        detailRow
          .querySelectorAll("[data-work-detail]")
          .forEach(function (item) {
            item.setAttribute("hidden", "");
          });

        if (alreadyOpen) {
          detailRow.setAttribute("hidden", "");
          return;
        }

        var item = detailRow.querySelector(
          '[data-work-detail="' + workId + '"]'
        );
        if (item) item.removeAttribute("hidden");
        detailRow.removeAttribute("hidden");
        btn.classList.add("is-open");
        btn.setAttribute("aria-expanded", "true");
      });
    });
  }

  function initProblemToggle() {
    document.querySelectorAll("[data-problem-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var packageId = btn.getAttribute("data-package-id");
        var problemId = btn.getAttribute("data-problem-id");
        var detailRow = document.querySelector(
          '[data-package-problem-detail="' + packageId + '"]'
        );
        if (!detailRow) return;

        var alreadyOpen =
          btn.classList.contains("is-open") &&
          !detailRow.hasAttribute("hidden");

        document
          .querySelectorAll(
            '[data-problem-toggle][data-package-id="' + packageId + '"]'
          )
          .forEach(function (b) {
            b.classList.remove("is-open");
            b.setAttribute("aria-expanded", "false");
          });
        detailRow
          .querySelectorAll("[data-problem-detail]")
          .forEach(function (item) {
            item.setAttribute("hidden", "");
          });

        if (alreadyOpen) {
          detailRow.setAttribute("hidden", "");
          return;
        }

        var item = detailRow.querySelector(
          '[data-problem-detail="' + problemId + '"]'
        );
        if (item) item.removeAttribute("hidden");
        detailRow.removeAttribute("hidden");
        btn.classList.add("is-open");
        btn.setAttribute("aria-expanded", "true");
      });
    });
  }

  function initTrainingToggle() {
    document.querySelectorAll("[data-training-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var packageId = btn.getAttribute("data-package-id");
        var trainingId = btn.getAttribute("data-training-id");
        var detailRow = document.querySelector(
          '[data-package-training-detail="' + packageId + '"]'
        );
        if (!detailRow) return;

        var alreadyOpen =
          btn.classList.contains("is-open") &&
          !detailRow.hasAttribute("hidden");

        document
          .querySelectorAll(
            '[data-training-toggle][data-package-id="' + packageId + '"]'
          )
          .forEach(function (b) {
            b.classList.remove("is-open");
            b.setAttribute("aria-expanded", "false");
          });
        detailRow
          .querySelectorAll("[data-training-detail]")
          .forEach(function (item) {
            item.setAttribute("hidden", "");
          });

        if (alreadyOpen) {
          detailRow.setAttribute("hidden", "");
          return;
        }

        var item = detailRow.querySelector(
          '[data-training-detail="' + trainingId + '"]'
        );
        if (item) item.removeAttribute("hidden");
        detailRow.removeAttribute("hidden");
        btn.classList.add("is-open");
        btn.setAttribute("aria-expanded", "true");
      });
    });
  }

  function setCardDetailsVisible(card, show) {
    if (!card) return;
    if (show) {
      card.classList.remove("section-card--collapsed");
    } else {
      card.classList.add("section-card--collapsed");
    }
    var btn = card.querySelector("[data-card-details-toggle]");
    if (btn) {
      btn.textContent = show ? "إخفاء التفاصيل" : "إظهار التفاصيل";
      btn.setAttribute("aria-expanded", show ? "true" : "false");
    }
  }

  function syncGlobalDetailsButton() {
    var globalBtn = document.querySelector("[data-details-toggle]");
    if (!globalBtn) return;
    var cards = document.querySelectorAll(".section-card");
    if (!cards.length) {
      globalBtn.textContent = "إخفاء التفاصيل";
      globalBtn.setAttribute("aria-pressed", "false");
      return;
    }
    var anyCollapsed = false;
    cards.forEach(function (card) {
      if (card.classList.contains("section-card--collapsed")) anyCollapsed = true;
    });
    // Global button: if any collapsed, offer "show all"; else "hide all"
    var allShown = !anyCollapsed;
    globalBtn.textContent = allShown ? "إخفاء التفاصيل" : "إظهار التفاصيل";
    globalBtn.setAttribute("aria-pressed", allShown ? "false" : "true");
  }

  function applyAllDetailsVisibility(show) {
    document.querySelectorAll(".section-card").forEach(function (card) {
      setCardDetailsVisible(card, show);
    });
    syncGlobalDetailsButton();
  }

  function initDetailsToggle() {
    document.querySelectorAll("[data-card-details-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".section-card");
        if (!card) return;
        var currentlyShown = !card.classList.contains("section-card--collapsed");
        setCardDetailsVisible(card, !currentlyShown);
        syncGlobalDetailsButton();
      });
    });

    var globalBtn = document.querySelector("[data-details-toggle]");
    if (!globalBtn) return;

    var show = true;
    try {
      var stored = localStorage.getItem(
        "sectionsDetailsVisible:" + location.pathname
      );
      if (stored === "0") show = false;
      if (stored === "1") show = true;
    } catch (e) {}
    applyAllDetailsVisibility(show);

    globalBtn.addEventListener("click", function () {
      var anyCollapsed = false;
      document.querySelectorAll(".section-card").forEach(function (card) {
        if (card.classList.contains("section-card--collapsed")) anyCollapsed = true;
      });
      var nextShow = anyCollapsed;
      applyAllDetailsVisibility(nextShow);
      try {
        localStorage.setItem(
          "sectionsDetailsVisible:" + location.pathname,
          nextShow ? "1" : "0"
        );
      } catch (e) {}
    });
  }

  function initSearchHitScroll() {
    var hit = document.querySelector("mark.search-hit");
    if (!hit) return;
    try {
      hit.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (e) {
      hit.scrollIntoView(false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initAutoFilters();
    initMultiPickers();
    initFloatWindows();
    initWorkTypeToggle();
    initProblemToggle();
    initTrainingToggle();
    initDetailsToggle();
    initSearchHitScroll();
  });
})();
