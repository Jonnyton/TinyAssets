(function () {
  const VAMIGA_ORIGIN = "https://vamigaweb.github.io";
  const VAMIGA_URL = `${VAMIGA_ORIGIN}/`;
  const ADF_URL = "./assets/scorched-tanks-v1.90-autostart-30582ca3.adf";
  const HOSTED_KICKSTART_URL = "./licensed/kickstart-a500-1.3.rom";
  const ADF_FILE_NAME = "scorched-tanks-v1.90-autostart.adf";
  const VAMIGA_RELOAD_SETTLE_MS = 1800;
  const DISK_INSERT_RETRY_DELAYS_MS = [300, 900, 1800, 3200];

  const installButton = document.getElementById("install-button");
  const fullscreenButton = document.getElementById(
    "emulator-fullscreen-button",
  );
  const arosButton = document.getElementById("start-aros-button");
  const kickstartButton = document.getElementById("start-kickstart-button");
  const resetButton = document.getElementById("reset-emulator-button");
  const kickstartInput = document.getElementById("kickstart-input");
  const emulatorFrameHost = document.getElementById("emulator-frame-host");
  const emulatorPanel = document.getElementById("emulator-panel");
  const runtimeStatus = document.getElementById("runtime-status");
  const mediaStatus = document.getElementById("media-status");
  const romStatus = document.getElementById("rom-status");
  const audioStatus = document.getElementById("audio-status");

  let installPrompt = null;
  let frame = null;
  let pollTimer = null;
  let launchTimer = null;
  let diskInsertTimers = [];
  let pendingLaunch = null;
  let currentLaunch = null;
  let kickstartRom = null;
  let adfBytes = null;
  let runtimeReady = false;
  let audioUnlocked = false;
  let lastFrameLoadAt = 0;
  let diskMountState = "idle";
  let diskMountGeneration = 0;

  const originalProof = {
    mode: "original-amiga",
    runtime: "vAmigaWeb",
    media: ADF_FILE_NAME,
    firmware: "not-started",
    mountState: diskMountState,
    mountAttempts: 0,
    runtimeReadyEvents: 0,
    frameLoads: 0,
    audioState: "locked",
    exactPlayable: false,
    blocker: "not-started",
  };

  window.__scorchedTanksOriginal = {
    getProof: () => JSON.parse(JSON.stringify(originalProof)),
  };

  function setRuntimeStatus(text) {
    runtimeStatus.textContent = text;
  }

  function setMediaStatus(text) {
    mediaStatus.textContent = text;
  }

  function setRomStatus(text) {
    romStatus.textContent = text;
  }

  function setAudioStatus(text) {
    audioStatus.textContent = text;
  }

  function setDiskMountState(state, blocker) {
    diskMountState = state;
    originalProof.mountState = state;
    if (arguments.length > 1) {
      originalProof.blocker = blocker;
    }
  }

  function reportAsync(task) {
    task.catch((error) => {
      setRuntimeStatus(error.message || "Runtime launch failed");
    });
  }

  function browserTouchMode() {
    return window.matchMedia("(pointer: coarse)").matches;
  }

  function emulatorSrc(config) {
    return `${VAMIGA_URL}#${encodeURIComponent(JSON.stringify(config))}`;
  }

  function absoluteAdfUrl() {
    return new URL(ADF_URL, window.location.href).href;
  }

  function absoluteHostedKickstartUrl() {
    return new URL(HOSTED_KICKSTART_URL, window.location.href).href;
  }

  function baseConfig(extra) {
    return {
      navbar: false,
      wide: true,
      display: "adaptive",
      border: false,
      dialog_on_disk: false,
      port2: true,
      touch: browserTouchMode(),
      warpto: 1200,
      ...extra,
    };
  }

  async function fetchBytes(url, missingIsNull = false) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      if (missingIsNull && response.status === 404) {
        return null;
      }
      throw new Error(`Unable to load ${url}`);
    }
    return new Uint8Array(await response.arrayBuffer());
  }

  async function loadAdfBytes() {
    if (!adfBytes) {
      setMediaStatus("Loading original ADF");
      adfBytes = await fetchBytes(absoluteAdfUrl());
    }
    return adfBytes;
  }

  async function loadHostedKickstartBytes() {
    return fetchBytes(absoluteHostedKickstartUrl(), true);
  }

  function clearPoller() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function clearLaunchTimer() {
    if (launchTimer) {
      window.clearTimeout(launchTimer);
      launchTimer = null;
    }
  }

  function clearDiskInsertTimers() {
    diskInsertTimers.forEach((timer) => window.clearTimeout(timer));
    diskInsertTimers = [];
  }

  function postToRuntime(message) {
    frame?.contentWindow?.postMessage(message, VAMIGA_ORIGIN);
  }

  function startPoller() {
    clearPoller();
    pollTimer = window.setInterval(() => {
      postToRuntime("poll_state");
    }, 700);
  }

  function insertInjectedDiskIntoDf0() {
    if (diskMountState === "mounted" || diskMountState === "already-mounted") {
      return;
    }

    const generation = diskMountGeneration;
    originalProof.mountAttempts += 1;
    setDiskMountState("mount-script-posted", null);
    postToRuntime({
      cmd: "script",
      script: `
        (() => {
          const generation = ${generation};
          const postMountState = (state, detail = "") => {
            try {
              window.parent.postMessage({
                msg: "scorched_original_mount",
                state,
                generation,
                detail
              }, "*");
            } catch (error) {
              console.error(error);
            }
          };

          if (
            typeof file_slot_file === "undefined" ||
            typeof file_slot_file_name === "undefined"
          ) {
            postMountState("slot-not-ready");
            return;
          }

          if (typeof wasm_has_disk === "function" && wasm_has_disk("df0")) {
            if (typeof show_drive_select === "function") {
              show_drive_select(false);
            }
            postMountState("already-mounted");
            if (
              typeof wasm_run === "function" &&
              typeof is_running === "function" &&
              !is_running()
            ) {
              setTimeout(() => {
                try { wasm_run(); } catch (error) { console.error(error); }
              }, 200);
            }
            return;
          }

          if (typeof insert_file === "function") {
            try {
              reset_before_load = true;
              insert_file(0);
              if (typeof show_drive_select === "function") {
                show_drive_select(false);
              }
              postMountState("mounted", "insert_file_reset");
              setTimeout(() => {
                try {
                  if (
                    typeof wasm_run === "function" &&
                    typeof is_running === "function" &&
                    !is_running()
                  ) {
                    wasm_run();
                  }
                } catch (error) {
                  console.error(error);
                }
              }, 250);
            } catch (error) {
              postMountState("mount-error", error?.message || String(error));
            }
            return;
          }

          if (typeof wasm_loadfile === "function") {
            try {
              wasm_loadfile(file_slot_file_name, file_slot_file, 0);
              if (typeof show_drive_select === "function") {
                show_drive_select(false);
              }
              if (typeof wasm_reset === "function") {
                wasm_reset();
              }
              postMountState("mounted", "wasm_loadfile_reset");
              setTimeout(() => {
                try { if (typeof wasm_run === "function") { wasm_run(); } }
                catch (error) { console.error(error); }
              }, 250);
            } catch (error) {
              postMountState("mount-error", error?.message || String(error));
            }
            return;
          }

          postMountState("runtime-api-not-ready");
        })();
      `,
    });
  }

  function unlockAudio() {
    if (audioUnlocked || !frame?.contentWindow) {
      return;
    }
    postToRuntime("toggle_audio()");
    setAudioStatus("Audio requested");
  }

  function scheduleDiskInsert(delay) {
    diskInsertTimers.push(window.setTimeout(insertInjectedDiskIntoDf0, delay));
  }

  function scheduleDiskInsertRetries() {
    clearDiskInsertTimers();
    DISK_INSERT_RETRY_DELAYS_MS.forEach(scheduleDiskInsert);
  }

  function scheduleLaunchInjection() {
    if (!pendingLaunch || !runtimeReady || !frame?.contentWindow) {
      return;
    }

    clearLaunchTimer();
    const msSinceFrameLoad = lastFrameLoadAt
      ? Date.now() - lastFrameLoadAt
      : 0;
    const delay = Math.max(0, VAMIGA_RELOAD_SETTLE_MS - msSinceFrameLoad);
    setRuntimeStatus("Runtime ready; loading original media");
    launchTimer = window.setTimeout(() => {
      launchTimer = null;
      injectLaunch();
    }, delay);
  }

  async function injectLaunch() {
    if (!pendingLaunch || !frame?.contentWindow) {
      return;
    }

    const launch = pendingLaunch;
    pendingLaunch = null;
    setRuntimeStatus("Injecting original media");

    try {
      const payload = {
        cmd: "load",
        file_name: ADF_FILE_NAME,
        file: launch.adfBytes,
      };

      if (launch.kickstartRom) {
        payload.kickstart_rom = launch.kickstartRom.bytes;
      }

      postToRuntime(payload);
      diskMountGeneration += 1;
      setDiskMountState("queued", null);
      scheduleDiskInsertRetries();
      setMediaStatus("Original v1.90 autostart ADF booting from df0");
      if (launch.kickstartRom) {
        originalProof.firmware = launch.kickstartRom.name;
        originalProof.blocker = "gameplay-proof-pending";
        setRuntimeStatus(`Running with ${launch.kickstartRom.name}`);
      } else {
        originalProof.firmware = "AROS Kickstart replacement";
        originalProof.blocker = "needs-rights-cleared-kickstart";
        setRuntimeStatus("Booting original disk with AROS");
      }
    } catch (error) {
      pendingLaunch = launch;
      setRuntimeStatus(error.message || "Media injection failed");
    }
  }

  function mountEmulator(config, launch) {
    pendingLaunch = launch;
    currentLaunch = launch;
    originalProof.firmware = launch.kickstartRom
      ? launch.kickstartRom.name
      : "AROS Kickstart replacement";
    originalProof.exactPlayable = false;
    originalProof.blocker = launch.kickstartRom
      ? "gameplay-proof-pending"
      : "needs-rights-cleared-kickstart";
    clearPoller();
    clearLaunchTimer();
    clearDiskInsertTimers();
    runtimeReady = false;
    setDiskMountState("idle", "runtime-loading");
    lastFrameLoadAt = 0;
    document.body.classList.remove("is-playing");
    emulatorFrameHost.textContent = "";
    frame = document.createElement("iframe");
    frame.id = "vAmigaWeb";
    frame.title = "vAmigaWeb running Scorched Tanks";
    frame.allow = "fullscreen; gamepad; autoplay";
    if ("credentialless" in frame) {
      frame.credentialless = true;
    }
    frame.src = emulatorSrc(config);
    frame.addEventListener("load", () => {
      setRuntimeStatus("Runtime booting");
      clearLaunchTimer();
      clearDiskInsertTimers();
      runtimeReady = false;
      audioUnlocked = false;
      lastFrameLoadAt = Date.now();
      originalProof.frameLoads += 1;
      if (!pendingLaunch && currentLaunch) {
        pendingLaunch = currentLaunch;
        setDiskMountState("idle", "runtime-reloaded");
        setMediaStatus("Runtime restarted; original disk queued");
      }
      document.body.classList.add("is-playing");
      startPoller();
    });
    emulatorFrameHost.appendChild(frame);
  }

  async function startWithHostedKickstart() {
    setRuntimeStatus("Checking hosted Kickstart");
    const [loadedAdfBytes, hostedKickstartBytes] = await Promise.all([
      loadAdfBytes(),
      loadHostedKickstartBytes(),
    ]);

    if (!hostedKickstartBytes) {
      return false;
    }

    setRomStatus("Licensed A500 Kickstart supplied by host");
    mountEmulator(
      baseConfig({
        AROS: false,
        wait_for_kickstart_injection: true,
      }),
      {
        adfBytes: loadedAdfBytes,
        kickstartRom: {
          name: "hosted Kickstart 1.3",
          bytes: hostedKickstartBytes,
        },
      },
    );
    return true;
  }

  async function startWithAros() {
    setRomStatus("AROS trial; exact play may need Kickstart 1.3");
    mountEmulator(
      baseConfig({
        AROS: true,
      }),
      { adfBytes: await loadAdfBytes(), kickstartRom: null },
    );
  }

  async function startPreferredRuntime() {
    try {
      const hosted = await startWithHostedKickstart();
      if (!hosted) {
        await startWithAros();
      }
    } catch (error) {
      setRuntimeStatus(error.message || "Runtime launch failed");
    }
  }

  async function startWithKickstart() {
    if (!kickstartRom) {
      setRomStatus("Choose a Kickstart ROM first");
      return;
    }

    mountEmulator(
      baseConfig({
        AROS: false,
        wait_for_kickstart_injection: true,
      }),
      { adfBytes: await loadAdfBytes(), kickstartRom },
    );
  }

  async function resetEmulator() {
    if (!frame) {
      await startPreferredRuntime();
      return;
    }
    const relaunch = pendingLaunch || currentLaunch || { kickstartRom };
    mountEmulator(
      baseConfig(
        relaunch.kickstartRom
          ? { AROS: false, wait_for_kickstart_injection: true }
          : { AROS: true },
      ),
      {
        adfBytes: relaunch.adfBytes || (await loadAdfBytes()),
        kickstartRom: relaunch.kickstartRom || null,
      },
    );
  }

  async function onKickstartSelected() {
    const [file] = kickstartInput.files || [];
    if (!file) {
      kickstartRom = null;
      kickstartButton.disabled = true;
      setRomStatus("No Kickstart ROM selected");
      return;
    }

    kickstartRom = {
      name: file.name,
      bytes: new Uint8Array(await file.arrayBuffer()),
    };
    kickstartButton.disabled = false;
    setRomStatus(`${file.name} ready locally`);
  }

  function bindInstall() {
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker
          .register("./service-worker.js", { scope: "./" })
          .catch(() => setRuntimeStatus("Offline cache unavailable"));
      });
    }

    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      installPrompt = event;
      installButton.disabled = false;
    });

    installButton.addEventListener("click", async () => {
      if (!installPrompt) {
        setRuntimeStatus("Use the browser menu to install this app");
        return;
      }
      installButton.disabled = true;
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      installButton.disabled = false;
    });
  }

  window.addEventListener("message", (event) => {
    if (
      event.origin !== VAMIGA_ORIGIN ||
      event.source !== frame?.contentWindow
    ) {
      return;
    }

    if (event.data?.msg === "render_run_state") {
      runtimeReady = true;
      originalProof.runtimeReadyEvents += 1;
      if (!pendingLaunch) {
        setRuntimeStatus(
          event.data.value
            ? currentLaunch?.kickstartRom
              ? "Running original disk"
              : "AROS diagnostic running"
            : "Runtime ready",
        );
        return;
      }
      scheduleLaunchInjection();
      return;
    }

    if (event.data?.msg === "render_current_audio_state") {
      const audioState = event.data.value || "unknown";
      audioUnlocked = audioState === "running";
      originalProof.audioState = audioState;
      setAudioStatus(
        audioState === "running" ? "Audio running" : `Audio ${audioState}`,
      );
    }

    if (event.data?.msg === "scorched_original_mount") {
      if (event.data.generation !== diskMountGeneration) {
        return;
      }

      if (
        event.data.state === "mounted" ||
        event.data.state === "already-mounted"
      ) {
        clearDiskInsertTimers();
        setDiskMountState(
          event.data.state,
          currentLaunch?.kickstartRom
            ? "gameplay-proof-pending"
            : "needs-rights-cleared-kickstart",
        );
        setMediaStatus("Original disk mounted in df0; booting");
        return;
      }

      setDiskMountState(
        event.data.state || "mount-unknown",
        event.data.detail || "mount-not-complete",
      );
    }
  });

  window.addEventListener("error", (event) => {
    setRuntimeStatus(event.message || "Runtime error");
  });

  fullscreenButton.addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
      return;
    }
    emulatorPanel.requestFullscreen?.();
  });

  arosButton.addEventListener("click", () => reportAsync(startWithAros()));
  kickstartButton.addEventListener("click", () =>
    reportAsync(startWithKickstart()),
  );
  resetButton.addEventListener("click", () => reportAsync(resetEmulator()));
  kickstartInput.addEventListener("change", onKickstartSelected);
  window.addEventListener("pointerdown", unlockAudio, { capture: true });
  window.addEventListener("keydown", unlockAudio, { capture: true });

  bindInstall();
  setMediaStatus("Original v1.90 autostart ADF ready");
  setAudioStatus("Audio locked");
  reportAsync(startPreferredRuntime());
})();
