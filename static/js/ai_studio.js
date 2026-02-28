/**
 * AI Studio – Forbidden Command Center
 * Clean rewrite: all symbols on window.*, no auto-init, no DOMContentLoaded.
 */

/* ── helpers ── */
window._sj = (typeof window.safeJSON !== "undefined")
  ? window.safeJSON
  : function (r) { return r.json(); };

window.toast = (typeof window.showToast === "function")
  ? window.showToast
  : function () {};

/* ── brand prompt prefixes ── */
window.BRAND_PREFIX = "A premium bourbon whiskey in a distinctive heavy glass 8-pointed star-shaped geometric decanter bottle. The bottle has sharp angular facets, fluted ridges, and a dark metallic label that reads 'FORBIDDEN' in elegant gold art deco lettering. The bourbon inside is dark amber/copper colored. The bottle has a heavy square stopper top. ";

window.BRAND_DETAIL = "The Forbidden Bourbon bottle is an art-deco geometric decanter with 8 pointed star cross-section, rigid angular lines cut into thick heavy glass, showing the dark amber bourbon inside. The label is dark with gold metallic 'FORBIDDEN' text in art deco font. ";

/* ── fallback image prompts ── */
window.IMAGE_PROMPTS_FALLBACK = {
  product: [
    "Dark marble surface, dramatic side lighting, smoky atmosphere",
    "Polished oak bar top, warm amber spotlights, blurred bar background",
    "Black slate surface with scattered ice crystals, rim lighting",
    "Aged leather desk, brass lamp, old books, warm library glow",
    "Raw wooden barrel top, dark moody warehouse background",
    "Clean white marble pedestal, studio lighting, luxury feel"
  ],
  lifestyle: [
    "Cozy fireside setting, warm orange glow, leather armchair visible",
    "Outdoor porch at golden hour sunset, Kentucky rolling hills",
    "Upscale restaurant table, candlelight, bokeh city lights behind",
    "Rustic cabin interior, stone fireplace, wool blanket draped nearby",
    "Gentleman's study with globe, dark wood shelving, warm lamplight",
    "Summer evening patio, string lights, warm breeze atmosphere"
  ],
  artdeco: [
    "Art deco geometric gold and black background, 1920s pattern",
    "Speakeasy interior, velvet curtains, brass fixtures, moody lighting",
    "Gold leaf textured wall, dramatic spotlight from above",
    "Gatsby-era black marble with gold geometric inlays",
    "Ornate gold frame on dark wall, gallery spotlight",
    "Black lacquer surface with gold flake accents, luxury aesthetic"
  ],
  cocktail: [
    "Bar setup with Old Fashioned ingredients: orange peel, cherry, bitters",
    "Cocktail prep station: muddler, jigger, ice sphere, crystal glass",
    "Mint Julep scene: crushed ice, silver cup, fresh mint sprigs",
    "Whiskey Sour setup: lemon, egg white, cherry, shaker",
    "Summer bar scene: ice bucket, citrus slices, copper tools",
    "Cheese and charcuterie board, walnut cutting board, warm lighting"
  ],
  social: [
    "Instagram-worthy flat lay: leather, watch, cigar, glasses",
    "Gift box scene: velvet lined box, ribbon, holiday setting",
    "Poolside luxury: marble edge, blue water, tropical plants",
    "Weekend brunch table, newspaper, coffee, warm morning light",
    "Party scene: confetti, gold accents, celebration mood",
    "Campfire glow, night sky, rustic outdoor setting"
  ],
  editorial: [
    "Magazine-style dark gradient backdrop, professional studio lighting",
    "Kentucky bourbon country landscape, rolling hills, golden hour",
    "Barrel aging warehouse, rows of oak barrels, shaft of light",
    "Close-up textured background: charred oak, grain detail",
    "Copper still room, industrial distillery equipment, steam",
    "Wheat field at golden hour, Kentucky countryside"
  ]
};

/* ── fallback video prompts ── */
window.VIDEO_PROMPTS_FALLBACK = {
  pour: [
    "Slow-motion bourbon pour into crystal glass",
    "Close-up pour over a single ice sphere",
    "Bourbon stream catching golden light",
    "Pouring a perfect Old Fashioned"
  ],
  glamour: [
    "Camera slowly orbiting the bottle",
    "Bottle reveal from shadow into spotlight",
    "Light rays moving across the bottle label",
    "Condensation drops on a chilled glass"
  ],
  bar: [
    "Bartender crafting a cocktail, moody lighting",
    "Sliding bourbon glass down a polished bar",
    "Ice placed into glass, then bourbon poured",
    "Two glasses clinking in warm ambiance"
  ],
  nature: [
    "Sunrise over Kentucky bourbon country",
    "Wheat swaying in warm breeze, golden hour",
    "Oak barrel in a field with morning fog",
    "Rain on barrel warehouse roof, cozy interior"
  ]
};

/* ── state ── */
window._apiVideoTemplates = null;
window._apiImageTemplates = null;
window.currentStyle = "product";
window.currentVideoStyle = "pour";
window.lastImagePrompt = "";
window.lastVideoPrompt = "";
window._galleryFilter = "all";
window._currentGalleryId = null;
window._currentImageSaved = false;

/* ── loadApiTemplates ── */
window.loadApiTemplates = function () {
  return fetch("/api/ai/templates")
    .then(window._sj)
    .then(function (data) {
      if (data && data.video) { window._apiVideoTemplates = data.video; }
      if (data && data.image) { window._apiImageTemplates = data.image; }
    })
    .catch(function () { /* fall back to hardcoded */ });
};

/* ── checkApiKeys ── */
window.checkApiKeys = function () {
  fetch("/api/ai/status")
    .then(window._sj)
    .then(function (data) {
      var dalleEl = document.getElementById("dalleStatus");
      var runwayEl = document.getElementById("runwayStatus");
      var keysBtn = document.getElementById("keysBtn");
      if (!dalleEl) return;
      dalleEl.innerHTML = data.openai
        ? '<span style="color:#4ade80;">● DALL-E Ready</span>'
        : '<span style="color:#f87171;">○ DALL-E — No Key</span>';
      runwayEl.innerHTML = data.runway
        ? '<span style="color:#4ade80;">● Runway Ready</span>'
        : '<span style="color:#f87171;">○ Runway — No Key</span>';
      if (!data.openai || !data.runway) {
        keysBtn.style.display = "";
      } else {
        keysBtn.style.display = "none";
        document.getElementById("settingsPanel").classList.add("hidden");
      }
    })
    .catch(function (err) {
      var d = document.getElementById("dalleStatus");
      var r = document.getElementById("runwayStatus");
      if (d) { d.innerHTML = '<span style="color:#f87171;">○ DALL-E — Error</span>'; }
      if (r) { r.innerHTML = '<span style="color:#f87171;">○ Runway — Error</span>'; }
      console.log("Status check error:", err);
    });
};

/* ── switchMode ── */
window.switchMode = function (mode, btn) {
  document.querySelectorAll(".filter-tab").forEach(function (t) {
    t.classList.remove("active");
  });
  btn.classList.add("active");
  document.getElementById("imageMode").classList.toggle("hidden", mode !== "image");
  document.getElementById("videoMode").classList.toggle("hidden", mode !== "video");
  document.getElementById("galleryMode").classList.toggle("hidden", mode !== "gallery");
  if (mode === "gallery") window.loadGallery();
};

/* ── selectStyle / selectVideoStyle ── */
window.selectStyle = function (btn) {
  document.querySelectorAll(".style-preset[data-style]").forEach(function (b) {
    b.classList.remove("active");
  });
  btn.classList.add("active");
  window.currentStyle = btn.dataset.style;
  window.loadPromptTemplates();
};

window.selectVideoStyle = function (btn) {
  document.querySelectorAll(".style-preset[data-vstyle]").forEach(function (b) {
    b.classList.remove("active");
  });
  btn.classList.add("active");
  window.currentVideoStyle = btn.dataset.vstyle;
  window.loadVideoPromptTemplates();
};

/* ── loadPromptTemplates ── */
window.loadPromptTemplates = function () {
  var c = document.getElementById("promptTemplates");
  var prompts;
  if (window._apiImageTemplates) {
    prompts = window._apiImageTemplates
      .filter(function (t) {
        return t.category === window.currentStyle ||
          t.category === (window.currentStyle === "artdeco" ? "brand" : window.currentStyle);
      })
      .map(function (t) { return t.prompt; });
    if (prompts.length === 0) {
      prompts = window._apiImageTemplates.map(function (t) { return t.prompt; }).slice(0, 6);
    }
  } else {
    prompts = window.IMAGE_PROMPTS_FALLBACK[window.currentStyle] || [];
  }
  c.innerHTML = prompts.map(function (p) {
    return '<button class="prompt-chip" onclick="usePrompt(this,\'image\')">' + p + "</button>";
  }).join("");
};

/* ── loadVideoPromptTemplates ── */
window.loadVideoPromptTemplates = function () {
  var c = document.getElementById("videoPromptTemplates");
  var prompts;
  if (window._apiVideoTemplates) {
    var catMap = { pour: "product", glamour: "product", bar: "lifestyle", nature: "heritage" };
    var cat = catMap[window.currentVideoStyle] || "product";
    var filtered = window._apiVideoTemplates.filter(function (t) {
      return t.category === cat;
    });
    if (filtered.length === 0) filtered = window._apiVideoTemplates.slice(0, 8);
    prompts = filtered.map(function (t) {
      return { label: t.label, prompt: t.prompt };
    });
    c.innerHTML = prompts.map(function (p) {
      return '<button class="prompt-chip" data-full-prompt="' +
        p.prompt.replace(/"/g, "&quot;") +
        '" onclick="useVideoTemplate(this)">' + p.label + "</button>";
    }).join("");
    return;
  }
  prompts = (window.VIDEO_PROMPTS_FALLBACK[window.currentVideoStyle] || []).map(function (p) {
    return { label: p, prompt: p };
  });
  c.innerHTML = prompts.map(function (p) {
    return '<button class="prompt-chip" onclick="usePrompt(this,\'video\')">' + p.label + "</button>";
  }).join("");
};

/* ── usePrompt / useVideoTemplate ── */
window.usePrompt = function (btn, type) {
  var ta = type === "video"
    ? document.getElementById("videoPrompt")
    : document.getElementById("imagePrompt");
  ta.value = btn.textContent;
  ta.focus();
};

window.useVideoTemplate = function (btn) {
  document.getElementById("videoPrompt").value = btn.dataset.fullPrompt || btn.textContent;
  document.getElementById("videoPrompt").focus();
};

/* ── generateImage ── */
window.generateImage = function () {
  var prompt = document.getElementById("imagePrompt").value.trim();
  if (!prompt) { window.toast("Enter a prompt first", "error"); return; }
  window.lastImagePrompt = prompt;

  var size = document.getElementById("imageSize").value;
  var quality = document.getElementById("imageQuality").value;
  var useRef = document.getElementById("useBottleRef").checked;
  var bottlePosition = document.getElementById("bottlePosition")
    ? document.getElementById("bottlePosition").value : "center";
  var bottleScale = document.getElementById("bottleScale")
    ? document.getElementById("bottleScale").value : "0.65";
  var bottleType = document.getElementById("bottleType")
    ? document.getElementById("bottleType").value : "small_batch";

  document.getElementById("imageResult").classList.remove("hidden");
  document.getElementById("imageLoading").classList.remove("hidden");
  document.getElementById("imageOutput").classList.add("hidden");
  document.getElementById("generateImageBtn").disabled = true;

  /* Show progress steps for composite mode */
  var stepsEl = document.getElementById("imageProgressSteps");
  var titleEl = document.getElementById("imageLoadingTitle");
  var timeEl = document.getElementById("imageLoadingTime");
  if (useRef) {
    stepsEl.classList.remove("hidden");
    titleEl.textContent = "Building scene around your bottle...";
    timeEl.textContent = "Composite mode takes 60-90 seconds";
    document.getElementById("step1").innerHTML = "⏳ Step 1: Cutting out bottle...";
    document.getElementById("step2").innerHTML = "○ Step 2: Generating background scene...";
    document.getElementById("step3").innerHTML = "○ Step 3: Compositing bottle onto scene...";
    document.getElementById("generateImageBtn").textContent = "Building scene around bottle...";
    /* Simulate progress updates */
    window._imgStep2Timer = setTimeout(function() {
      document.getElementById("step1").innerHTML = "✅ Step 1: Bottle cutout ready";
      document.getElementById("step2").innerHTML = "⏳ Step 2: Generating background scene...";
    }, 8000);
    window._imgStep3Timer = setTimeout(function() {
      document.getElementById("step2").innerHTML = "✅ Step 2: Background scene generated";
      document.getElementById("step3").innerHTML = "⏳ Step 3: Compositing bottle onto scene...";
    }, 35000);
  } else {
    stepsEl.classList.add("hidden");
    titleEl.textContent = "Generating your image...";
    timeEl.textContent = "This takes 15-30 seconds";
    document.getElementById("generateImageBtn").textContent = "Generating...";
  }

  var fullPrompt = prompt;
  if (!useRef) {
    fullPrompt = window.BRAND_DETAIL + prompt +
      ". Professional product photography, luxury spirits brand aesthetic.";
  }

  fetch("/api/ai/generate-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: fullPrompt,
      size: size,
      quality: quality,
      use_reference: useRef,
      bottle_position: bottlePosition,
      bottle_scale: parseFloat(bottleScale),
      bottle_type: bottleType
    })
  })
    .then(window._sj)
    .then(function (data) {
      document.getElementById("imageLoading").classList.add("hidden");
      document.getElementById("generateImageBtn").disabled = false;
      document.getElementById("generateImageBtn").textContent = "✦ Generate Image";
      clearTimeout(window._imgStep2Timer);
      clearTimeout(window._imgStep3Timer);

      if (data.error) {
        document.getElementById("imageError").classList.remove("hidden");
        document.getElementById("imageErrorDetail").textContent = data.error;
        document.getElementById("imageOutput").classList.remove("hidden");
        document.getElementById("generatedImage").style.display = "none";
        window.toast(data.error, "error");
        return;
      }
      if (!data.image_url) {
        document.getElementById("imageError").classList.remove("hidden");
        document.getElementById("imageErrorDetail").textContent = "No image URL in response";
        document.getElementById("imageOutput").classList.remove("hidden");
        document.getElementById("generatedImage").style.display = "none";
        window.toast("No image returned", "error");
        return;
      }

      document.getElementById("imageError").classList.add("hidden");
      document.getElementById("generatedImage").style.display = "";
      document.getElementById("generatedImage").src = data.image_url;
      document.getElementById("imageOutput").classList.remove("hidden");
      window._currentGalleryId = data.gallery_id || null;
      window._currentImageSaved = false;
      document.getElementById("favBtn").textContent = "⭐ Favorite";
      document.getElementById("favBtn").style.background = "";
      var modelMsg = data.model ? " (" + data.model + ")" : "";
      window.toast("Image generated!" + modelMsg, "success");
    })
    .catch(function (err) {
      document.getElementById("imageLoading").classList.add("hidden");
      document.getElementById("generateImageBtn").disabled = false;
      document.getElementById("generateImageBtn").textContent = "✦ Generate Image";
      clearTimeout(window._imgStep2Timer);
      clearTimeout(window._imgStep3Timer);
      document.getElementById("imageError").classList.remove("hidden");
      document.getElementById("imageErrorDetail").textContent = err.message;
      document.getElementById("imageOutput").classList.remove("hidden");
      document.getElementById("generatedImage").style.display = "none";
      window.toast("Failed: " + err.message, "error");
    });
};

window.regenerateImage = function () {
  document.getElementById("imagePrompt").value = window.lastImagePrompt;
  window.generateImage();
};

window.downloadImage = function () {
  var a = document.createElement("a");
  a.href = document.getElementById("generatedImage").src;
  a.download = "forbidden-ai-" + Date.now() + ".png";
  a.click();
};

/* saveToPhone: mobile-friendly save that doesn't navigate away */
window.saveToPhone = function () {
  var imgSrc = document.getElementById("generatedImage").src;
  /* On iOS Safari, anchor download doesn't work — fetch as blob */
  window.toast("Preparing download...", "info");
  fetch(imgSrc)
    .then(function (r) { return r.blob(); })
    .then(function (blob) {
      /* Try blob download first */
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "forbidden-ai-" + Date.now() + ".png";
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 200);
      window.toast("Image saved! Check your Downloads.", "success");
    })
    .catch(function () {
      /* Fallback: open in new tab so user can long-press to save */
      window.open(imgSrc, "_blank");
      window.toast("Long-press the image to save it to your phone.", "info");
    });
};

window.copyImageUrl = function () {
  navigator.clipboard.writeText(document.getElementById("generatedImage").src).then(function () {
    window.toast("URL copied!", "success");
  });
};

/* ── generateVideo ── */
window.generateVideo = function () {
  var prompt = document.getElementById("videoPrompt").value.trim();
  if (!prompt) { window.toast("Enter a prompt first", "error"); return; }
  window.lastVideoPrompt = prompt;

  var duration = document.getElementById("videoDuration").value;
  var sourceSelect = document.getElementById("videoSourceImage");
  var sourceImage = sourceSelect ? sourceSelect.value : "";

  document.getElementById("videoResult").classList.remove("hidden");
  document.getElementById("videoLoading").classList.remove("hidden");
  document.getElementById("videoOutput").classList.add("hidden");
  document.getElementById("generateVideoBtn").disabled = true;
  document.getElementById("generateVideoBtn").textContent = "Generating...";
  document.getElementById("videoStatus").textContent = "";

  /* Progress steps */
  document.getElementById("vstep1").innerHTML = "⏳ Step 1: Preparing source image...";
  document.getElementById("vstep2").innerHTML = "○ Step 2: Submitting to Runway...";
  document.getElementById("vstep3").innerHTML = "○ Step 3: Rendering video...";
  document.getElementById("vstep4").innerHTML = "○ Step 4: Downloading & processing...";

  /* Elapsed timer */
  var videoStartTime = Date.now();
  window._videoElapsedTimer = setInterval(function () {
    var elapsed = Math.round((Date.now() - videoStartTime) / 1000);
    var el = document.getElementById("videoElapsed");
    if (el) el.textContent = elapsed + "s elapsed";
  }, 1000);

  var fullPrompt;
  if (sourceImage) {
    fullPrompt = prompt + ". Cinematic, warm golden and dark tones, luxury spirits commercial.";
  } else {
    fullPrompt = "Forbidden Bourbon premium whiskey bottle, " + prompt +
      ". Cinematic, luxury brand aesthetic, warm golden and dark tones.";
  }

  var payload = { prompt: fullPrompt, duration: parseInt(duration) };
  if (sourceImage) {
    payload.source_image = window.location.origin + sourceImage;
  }

  fetch("/api/ai/generate-video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
    .then(window._sj)
    .then(function (data) {
      if (data.error) {
        document.getElementById("videoLoading").classList.add("hidden");
        document.getElementById("generateVideoBtn").disabled = false;
        document.getElementById("generateVideoBtn").textContent = "🎬 Generate Video";
        window.toast(data.error, "error");
        document.getElementById("videoResult").classList.add("hidden");
        return;
      }
      if (data.task_id) {
        document.getElementById("vstep1").innerHTML = "✅ Step 1: Source image ready";
        document.getElementById("vstep2").innerHTML = "✅ Step 2: Submitted to Runway";
        document.getElementById("vstep3").innerHTML = "⏳ Step 3: Rendering video...";
        window.pollVideoStatus(data.task_id, data.provider || 'runway');
      } else if (data.video_url) {
        window.showVideoResult(data.video_url);
      }
    })
    .catch(function (err) {
      clearInterval(window._videoElapsedTimer);
      document.getElementById("videoLoading").classList.add("hidden");
      document.getElementById("generateVideoBtn").disabled = false;
      document.getElementById("generateVideoBtn").textContent = "🎬 Generate Video";
      window.toast("Failed: " + err.message, "error");
    });
};

/* ── pollVideoStatus ── */
window.pollVideoStatus = function (taskId, provider) {
  provider = provider || 'runway';
  document.getElementById("videoStatus").textContent = "Processing video...";
  var interval = setInterval(function () {
    fetch("/api/ai/video-status/" + taskId + "?provider=" + provider)
      .then(window._sj)
      .then(function (data) {
        if (data.status === "SUCCEEDED" && data.video_url) {
          clearInterval(interval);
          window.showVideoResult(data.video_url);
        } else if (data.status === "FAILED") {
          clearInterval(interval);
          clearInterval(window._videoElapsedTimer);
          document.getElementById("videoLoading").classList.add("hidden");
          document.getElementById("generateVideoBtn").disabled = false;
          document.getElementById("generateVideoBtn").textContent = "🎬 Generate Video";
          window.toast("Video generation failed", "error");
        } else {
          document.getElementById("videoStatus").textContent =
            "Status: " + (data.status || "processing") + "...";
        }
      })
      .catch(function (err) {
        console.log("Video poll error:", err);
      });
  }, 5000);
  setTimeout(function () { clearInterval(interval); }, 300000);
};

/* ── showVideoResult ── */
window.showVideoResult = function (url) {
  clearInterval(window._videoElapsedTimer);
  document.getElementById("videoLoading").classList.add("hidden");
  document.getElementById("generateVideoBtn").disabled = false;
  document.getElementById("generateVideoBtn").textContent = "🎬 Generate Video";
  var video = document.getElementById("generatedVideo");
  video.src = url;
  video.load();
  document.getElementById("videoOutput").classList.remove("hidden");
  window.toast("Video generated!", "success");
};

window.regenerateVideo = function () {
  document.getElementById("videoPrompt").value = window.lastVideoPrompt;
  window.generateVideo();
};

window.downloadVideo = function () {
  var a = document.createElement("a");
  a.href = document.getElementById("generatedVideo").src;
  a.download = "forbidden-ai-" + Date.now() + ".mp4";
  a.click();
};

/* saveVideoToPhone: mobile-friendly video save */
window.saveVideoToPhone = function () {
  var vidSrc = document.getElementById("generatedVideo").src;
  window.toast("Preparing video download...", "info");
  fetch(vidSrc)
    .then(function (r) { return r.blob(); })
    .then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "forbidden-ai-" + Date.now() + ".mp4";
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 200);
      window.toast("Video saved! Check your Downloads.", "success");
    })
    .catch(function () {
      window.open(vidSrc, "_blank");
      window.toast("Long-press the video to save it to your phone.", "info");
    });
};

/* ── toggleFavorite ── */
window.toggleFavorite = function () {
  var id = window._currentGalleryId;
  if (!id) { window.toast("Generate an image first", "error"); return; }
  var newSaved = !window._currentImageSaved;
  fetch("/api/ai/save-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: id, saved: newSaved })
  })
    .then(window._sj)
    .then(function (data) {
      if (data.success) {
        window._currentImageSaved = newSaved;
        document.getElementById("favBtn").textContent = newSaved ? "⭐ Favorited!" : "⭐ Favorite";
        document.getElementById("favBtn").style.background = newSaved
          ? "linear-gradient(135deg, rgba(200,164,94,0.3), var(--bg-card))"
          : "";
        window.toast(newSaved ? "Added to favorites!" : "Removed from favorites", "success");
      }
    })
    .catch(function (err) { window.toast("Failed to save: " + err.message, "error"); });
};

/* ── loadGallery ── */
window.loadGallery = function (filter) {
  filter = filter || window._galleryFilter;
  window._galleryFilter = filter;
  document.getElementById("galAllBtn").className =
    filter === "all" ? "btn btn-primary btn-sm" : "btn btn-sm";
  document.getElementById("galSavedBtn").className =
    filter === "saved" ? "btn btn-primary btn-sm" : "btn btn-sm";

  var url = "/api/ai/gallery" + (filter === "saved" ? "?saved=true" : "");
  fetch(url)
    .then(window._sj)
    .then(function (data) {
      var grid = document.getElementById("galleryGrid");
      if (!data.items || data.items.length === 0) {
        var msg = filter === "saved"
          ? '<p style="font-size:0.96rem;">No favorites yet</p><p style="font-size:0.94rem;margin-top:4px;">⭐ Favorite your best images to save them here</p>'
          : '<p style="font-size:0.96rem;">No generated content yet</p><p style="font-size:0.94rem;margin-top:4px;">Generate images or videos to build your library</p>';
        grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">' + msg + "</div>";
        return;
      }
      grid.innerHTML = data.items.map(function (item) {
        var shortPrompt = (item.prompt || "").substring(0, 30) +
          (item.prompt && item.prompt.length > 30 ? "..." : "");
        var savedStar = item.saved
          ? '<span style="position:absolute;top:6px;right:6px;font-size:1.1rem;text-shadow:0 1px 3px rgba(0,0,0,0.8);">⭐</span>'
          : "";
        var bottleTag = item.bottle_type
          ? '<span style="position:absolute;top:6px;left:6px;font-size:0.7rem;background:rgba(0,0,0,0.6);color:var(--gold);padding:2px 6px;border-radius:4px;">' +
            (item.bottle_type === "single_barrel" ? "SGL" : "SB") + "</span>"
          : "";

        if (item.type === "video") {
          var isLocal = item.url &&
            (item.url.startsWith("/api/video/") || item.url.startsWith("/static/uploads/"));
          var playUrl = item.url;
          if (item.url && item.url.startsWith("/static/uploads/video_final_")) {
            playUrl = item.url.replace("/static/uploads/", "/api/video/");
          }
          var expiredBadge = !isLocal
            ? '<div style="position:absolute;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;font-size:0.75rem;color:#f87171;">⚠ Expired CDN</div>'
            : "";
          return '<div style="position:relative;border-radius:var(--radius-md);overflow:hidden;background:var(--bg-card);border:1px solid var(--border);cursor:pointer;" onclick="openVideoLightbox(\'' +
            playUrl + '\')">' +
            '<video src="' + (isLocal ? playUrl : "") +
            '" style="width:100%;height:180px;object-fit:cover;" muted preload="metadata"></video>' +
            expiredBadge + savedStar +
            '<div style="padding:6px 8px;font-size:0.8rem;color:var(--text-muted);">🎬 ' + shortPrompt + "</div></div>";
        }

        var saveBtn = item.id
          ? '<button onclick="event.stopPropagation();galToggleSave(' + item.id + "," +
            (!item.saved) + ',this)" style="position:absolute;bottom:32px;right:6px;background:rgba(0,0,0,0.6);border:none;color:white;font-size:0.9rem;padding:3px 6px;border-radius:4px;cursor:pointer;">' +
            (item.saved ? "⭐" : "☆") + "</button>"
          : "";
        return '<div style="position:relative;border-radius:var(--radius-md);overflow:hidden;background:var(--bg-card);border:1px solid var(--border);cursor:pointer;" onclick="window.open(\'' +
          item.url + '\')">' +
          '<img src="' + item.url + '" loading="lazy" style="width:100%;height:180px;object-fit:cover;">' +
          savedStar + bottleTag + saveBtn +
          '<div style="padding:6px 8px;font-size:0.8rem;color:var(--text-muted);">🎨 ' + shortPrompt + "</div></div>";
      }).join("");
    })
    .catch(function (err) {
      var grid = document.getElementById("galleryGrid");
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);"><p>Failed to load gallery</p></div>';
      console.log("Gallery load error:", err);
    });
};

/* ── video lightbox ── */
window.openVideoLightbox = function (url) {
  if (!url) { window.toast("Video URL expired — regenerate this video", "error"); return; }
  var lb = document.getElementById("videoLightbox");
  var vid = document.getElementById("lightboxVideo");
  vid.src = url;
  vid.load();
  lb.style.display = "flex";
  document.body.style.overflow = "hidden";
};

window.closeVideoLightbox = function (e) {
  if (e && e.target !== document.getElementById("videoLightbox") &&
      !e.target.closest('button[onclick="closeVideoLightbox()"]')) return;
  var vid = document.getElementById("lightboxVideo");
  vid.pause();
  vid.src = "";
  document.getElementById("videoLightbox").style.display = "none";
  document.body.style.overflow = "";
};

/* ── galToggleSave ── */
window.galToggleSave = function (id, saved, btn) {
  fetch("/api/ai/save-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: id, saved: saved })
  })
    .then(window._sj)
    .then(function (data) {
      if (data.success) {
        window.toast(saved ? "Added to favorites!" : "Removed from favorites", "success");
        window.loadGallery();
      }
    })
    .catch(function (err) { window.toast("Failed: " + err.message, "error"); });
};

/* ── saveKey ── */
window.saveKey = function (provider) {
  var key = provider === "openai"
    ? document.getElementById("openaiKey").value.trim()
    : document.getElementById("runwayKey").value.trim();
  if (!key) { window.toast("Enter a key first", "error"); return; }
  fetch("/api/ai/save-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: provider, key: key })
  })
    .then(window._sj)
    .then(function (data) {
      if (data.success) {
        window.toast(provider + " key saved!", "success");
        window.checkApiKeys();
        document.getElementById(provider === "openai" ? "openaiKey" : "runwayKey").value = "";
      } else {
        window.toast(data.error || "Failed", "error");
      }
    });
};
