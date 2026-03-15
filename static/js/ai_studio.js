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
    "Polished obsidian black marble counter, single concentrated warm amber spotlight from directly above creating a focused pool of light, ultra-shallow depth of field, scattered warm golden bokeh lights in deep background, atmospheric haze catching the light, commercial spirits photography",
    "Jet black seamless studio backdrop, dramatic dual rim lighting in warm gold from both sides creating edge highlights, polished dark reflective surface beneath, subtle smoke wisps drifting through the beam, luxury product photography setup",
    "Dark polished granite surface with natural veining, warm overhead pendant light creating a sharp spotlight circle, deep black negative space around, crystal decanter blurred in far background, premium spirits editorial lighting",
    "Matte black surface with single dramatic sidelight casting long warm shadows, atmospheric dust particles visible in the light beam, deep contrast between light and shadow, minimalist luxury aesthetic, commercial photography",
    "Dark brushed metal surface, three warm amber spotlights from above at different heights creating layered illumination, subtle reflection on surface, clean modern luxury environment, no clutter",
    "Polished black mirror surface creating perfect reflection, single warm overhead spotlight, absolute darkness everywhere else, smoke tendrils rising slowly, ultra-premium product photography aesthetic"
  ],
  lifestyle: [
    "Dramatic dark environment with warm fireplace glow casting amber light from behind, polished dark wood surface, leather wingback chair edge visible in soft bokeh, old world gentleman library atmosphere, single overhead warm spotlight on surface center, shallow depth of field",
    "Upscale speakeasy interior, dark walnut wood surfaces, crystal glassware hanging overhead catching warm light, amber pendant lighting creating bokeh, polished dark marble bar counter, atmospheric moody lighting, luxury after-dark vibe",
    "Private cigar lounge, deep mahogany paneling, warm sconce lighting creating golden pools, leather club chair armrest visible at edge, dark polished table surface, wisps of smoke in warm light, exclusive members-only atmosphere",
    "Kentucky distillery tasting room, charred oak barrel used as table surface, warm golden light filtering through aged wooden shutters, copper still visible in bokeh background, heritage bourbon atmosphere, shallow depth of field",
    "Candlelit private dining alcove, dark velvet curtains framing the background, polished black table surface with warm reflections, crystal wine glasses in soft focus nearby, intimate luxury dining atmosphere, warm amber color palette",
    "Rooftop lounge at twilight, polished dark stone surface, city skyline lights creating warm bokeh behind, single warm overhead spotlight, sophisticated urban nightlife setting, golden hour fading to blue hour"
  ],
  artdeco: [
    "1920s speakeasy interior with dark polished bar, brass Art Deco fixtures catching warm light, beveled mirrors creating depth, dark green velvet and gold accents, single warm spotlight from ornate ceiling fixture, moody Prohibition-era atmosphere",
    "Art Deco black marble surface with gold geometric inlays, dramatic overhead spotlight creating sharp light pool, dark mirrored wall behind with gold chevron pattern in soft focus, Gatsby-era luxury, warm amber color temperature",
    "Grand hotel bar with Art Deco columns, dark lacquered surface with gold trim, crystal chandelier creating warm bokeh above, polished brass rail in foreground, 1920s elegance and opulence, theatrical lighting",
    "Dark Art Deco lounge with geometric gold ceiling pattern casting patterned shadows, polished black onyx surface, warm spotlight from brass fixture above, velvet and gold everywhere in soft background, jazz-age sophistication",
    "Ornate gold-framed mirror behind dark marble surface creating infinite depth, Art Deco geometric wall sconces casting warm angular light patterns, black and gold color palette, old money luxury atmosphere",
    "Sleek black lacquer surface with inlaid gold leaf Art Deco sunburst pattern, dramatic single sidelight creating long shadows, dark mirrored background with warm reflections, timeless 1920s glamour"
  ],
  cocktail: [
    "Polished dark marble bar counter with Old Fashioned ingredients artfully arranged: Luxardo cherry, orange peel curl, crystal mixing glass, gold jigger, large clear ice sphere — all in soft focus, warm overhead bar lighting, single clear spot for the bottle in center",
    "Mixologist's station: dark walnut bar surface, copper barware catching warm light, fresh citrus and herbs in soft focus, crystal rocks glasses nearby, atmospheric bar lighting with warm bokeh, space cleared in center for hero product",
    "After-hours cocktail bar, dark polished surface with condensation droplets catching light, crystal coupe glass in soft bokeh nearby, warm amber backlighting from shelved bottles behind, intimate late-night atmosphere",
    "Whiskey tasting flight setup: dark slate board with three crystal nosing glasses in soft focus, warm overhead spotlight illuminating center surface, tasting notes card barely visible, premium spirits tasting room atmosphere",
    "Kentucky Derby scene: silver mint julep cups in soft background, crushed ice glistening, fresh mint sprigs, dark polished wooden surface, warm golden afternoon light, Southern hospitality luxury",
    "Dark stone surface with charcuterie board edge visible in background, aged cheese and dark chocolate in soft focus, warm candlelight creating intimate atmosphere, food and spirits pairing editorial setup"
  ],
  social: [
    "Elegant flat lay on dark leather surface: luxury watch, premium cigar in ashtray, dark sunglasses, all in soft focus framing center space — warm overhead spotlight, Instagram editorial aesthetic, shallow depth of field",
    "Premium gift box scene: dark velvet-lined box, gold ribbon, dark tissue paper, warm holiday lighting creating bokeh, polished dark surface, luxury unboxing moment, aspirational gifting aesthetic",
    "Dark poolside marble edge at golden hour, turquoise water blurred in background creating color contrast with warm amber tones, tropical plants in soft focus, summer luxury lifestyle, warm natural light",
    "Dark wood desk with leather journal, fountain pen, and reading glasses in soft focus, warm desk lamp creating focused pool of light, study atmosphere, thoughtful weekend moment, premium lifestyle",
    "New Year's celebration: dark polished surface, gold confetti and streamers in soft focus, champagne flutes catching warm light nearby, midnight celebration mood, aspirational party scene",
    "Campfire ember glow illuminating a dark rustic wooden surface, starry night sky visible in deep background bokeh, outdoor wilderness luxury, warm firelight creating dramatic shadows"
  ],
  editorial: [
    "Professional studio with infinite black backdrop, three-point lighting setup: warm key light from above, cool fill from left, warm rim from right, polished dark plexiglass surface creating mirror reflection, magazine cover photography",
    "Kentucky bourbon country: weathered oak fence in foreground with rolling green hills and golden sunset behind, warm afternoon light, editorial landscape setting with dark surface in immediate foreground for product placement",
    "Barrel aging warehouse interior, rows of charred oak barrels stretching into darkness, single shaft of warm golden light cutting through, barrel top surface in foreground, heritage and craftsmanship narrative, editorial documentary style",
    "Extreme close-up textured background: charred oak stave grain detail filling the background, warm sidelight creating texture shadows, dark polished surface in foreground, tactile craft story, macro editorial photography",
    "Copper pot still room in working distillery, industrial copper equipment catching warm light, steam rising, dark concrete surface in foreground, artisan production atmosphere, documentary editorial lighting",
    "Kentucky wheat field at golden hour, dark wooden fence post surface in immediate foreground, warm sun backlighting the grain, editorial landscape photography, amber and gold color palette throughout"
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
    "Camera slowly orbits the Forbidden bottle 360 degrees, dark background, warm spotlight",
    "Dramatic slow push-in toward the FORBIDDEN label, label comes into sharp focus",
    "Golden spotlight sweeps left to right across the bottle, amber bourbon glowing",
    "Bottle emerges from darkness as a single beam of light slowly illuminates it",
    "Camera pulls back from extreme close-up of label to reveal full bottle beauty",
    "Soft smoke or mist slowly drifts past the bottle, moody dark atmosphere",
    "Bottle rotates slowly as rim lighting traces the faceted glass edges",
    "Camera cranes down from above the bottle cap to label level, dramatic reveal",
    "Pulsing warm glow emanates from inside the bottle, amber bourbon radiant",
    "Bottle sits on reflective black marble, slow camera slide across the surface",
    "Sparkling light particles drift slowly past the bottle like gold dust",
    "Camera dollies slowly around the bottle, bokeh bar lights in background",
    "Dramatic underlit shot, light rises from below illuminating the bourbon inside",
    "Two Forbidden bottles side by side, camera slowly pulls back to reveal both",
    "Bottle on aged oak barrel, camera slowly circles in misty warehouse light",
    "Close-up of faceted bottle glass catching prismatic light, slow rotation",
    "Moonlight beam cuts through darkness and illuminates the Forbidden label",
    "Bottle on ice-frosted surface, cold breath mist rises around it slowly",
    "Camera tilts up from marble base to bottle cap, reverent slow reveal",
    "Cinematic lens flare sweeps across the bottle as light source moves behind it"
  ],
  bar: [
    "Slow cinematic dolly along a polished dark marble bar, warm amber backlighting from shelved bottles, atmospheric haze, bottle centered and fully in frame throughout, luxury cocktail bar atmosphere",
    "Camera slowly slides left to right past crystal barware catching warm light, bottle stays centered as foreground elements pass in soft focus, moody speakeasy atmosphere",
    "Warm spotlight slowly intensifies on the bottle sitting on dark bar surface, bokeh bar lights gently shift in background, subtle condensation glistens, intimate nightclub atmosphere",
    "Bartender's hands in soft focus placing a crystal glass next to the bottle, warm overhead lighting, cinematic shallow depth of field, slow deliberate motion"
  ],
  nature: [
    "Golden hour sunlight slowly sweeps across a weathered oak surface, warm lens flare builds from the right side, Kentucky rolling hills in soft bokeh background, bottle stays centered and sharp",
    "Morning mist slowly drifts through a bourbon rickhouse, shafts of warm light gradually illuminate the scene, bottle on barrel top in sharp focus, atmospheric and cinematic",
    "Camera slowly cranes down from charred oak barrel tops to reveal the bottle, warm golden light filtering through warehouse gaps, dust particles floating in light beams",
    "Gentle Kentucky breeze moves wheat stalks in soft background bokeh while bottle sits steady on dark fence post surface in foreground, golden hour light warming the scene"
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
  if (mode === "video") window.loadVideoPromptTemplates();
  if (mode === "image") window.loadPromptTemplates();
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
    var display = p.length > 60 ? p.substring(0, 57) + "..." : p;
    return '<button class="prompt-chip" title="' + p.replace(/"/g, '&quot;') + '" data-full="' + p.replace(/"/g, '&quot;') + '" onclick="usePrompt(this,\'image\')">' + display + "</button>";
  }).join("");
};

/* ── loadVideoPromptTemplates ── */
window.loadVideoPromptTemplates = function () {
  var c = document.getElementById("videoPromptTemplates");
  var prompts;
  if (window._apiVideoTemplates) {
    var catMap = {
      pour: ["product", "brand"],
      glamour: ["product", "brand", "social"],
      bar: ["lifestyle", "social"],
      nature: ["heritage"]
    };
    var cats = catMap[window.currentVideoStyle] || ["product"];
    var filtered = window._apiVideoTemplates.filter(function (t) {
      return cats.indexOf(t.category) !== -1;
    });
    if (filtered.length === 0) filtered = window._apiVideoTemplates.slice(0, 10);
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
  ta.value = btn.dataset.full || btn.textContent;
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
      try { window.loadRecentGallery(); } catch(e) {}
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

/* ── loadRecentGallery ── */
window.loadRecentGallery = function () {
  fetch("/api/ai/gallery?limit=5")
    .then(window._sj)
    .then(function (data) {
      var container = document.getElementById("recentGalleryRow");
      var wrapper = document.getElementById("recentGallery");
      if (!container || !wrapper) return;
      var images = (data.items || []).filter(function (i) { return i.type === "image" && i.url; });
      if (images.length === 0) { wrapper.style.display = "none"; return; }
      wrapper.style.display = "";
      container.innerHTML = images.map(function (item) {
        return '<img src="' + item.url + '" alt="Recent" title="' +
          (item.prompt || "").replace(/"/g, "&quot;") +
          '" style="width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid var(--border);cursor:pointer;flex-shrink:0;" onclick="window.open(\'' +
          item.url + '\')" loading="lazy">';
      }).join("");
    })
    .catch(function () {});
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
