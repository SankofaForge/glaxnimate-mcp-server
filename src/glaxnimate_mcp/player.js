(function () {
  "use strict";
  const svg = document.getElementById(__ROOT_ID__);
  const options = __OPTIONS__;
  const duration = options.duration_ms;
  const initialDirection = options.direction;
  const media = matchMedia("(prefers-reduced-motion: reduce)");
  let direction = initialDirection;
  let position = direction === 1 ? 0 : duration;
  let speed = options.speed;
  let running = false;
  let frame = 0;
  let previous = null;
  let cycles = 0;
  let observer = null;
  let destroyed = false;
  const animations = [...svg.querySelectorAll("animate, animateTransform, animateMotion")]
    .map(node => ({node, parent: node.parentNode}));
  svg.pauseAnimations();

  function render() {
    svg.setCurrentTime(position / 1000);
  }
  function emit(name) {
    svg.dispatchEvent(new CustomEvent("glaxnimate:" + name, {detail: {time: position}}));
  }
  function pause() {
    running = false;
    cancelAnimationFrame(frame);
    previous = null;
  }
  function tick(now) {
    if (!running) return;
    if (previous === null) previous = now;
    position += (now - previous) * speed * direction;
    previous = now;
    const atEnd = direction === 1 ? position >= duration : position <= 0;
    if (atEnd) {
      const excess = direction === 1 ? position - duration : -position;
      const passed = 1 + Math.floor(excess / duration);
      position = direction === 1 ? duration : 0;
      const remaining = options.iterations - cycles;
      if (options.iterations !== 0 && passed >= remaining) {
        if (options.alternate && (remaining - 1) % 2 !== 0) {
          direction *= -1;
          position = direction === 1 ? duration : 0;
        }
        cycles = options.iterations;
        pause();
        render();
        emit("finish");
        return;
      }
      cycles += passed;
      if (options.alternate && passed % 2 !== 0) direction *= -1;
      const remainder = excess % duration;
      position = direction === 1 ? remainder : duration - remainder;
      emit("repeat");
    }
    render();
    frame = requestAnimationFrame(tick);
  }
  function play() {
    if (destroyed || running || media.matches) return;
    running = true;
    previous = null;
    frame = requestAnimationFrame(tick);
    emit("play");
  }
  function reset() {
    pause();
    direction = initialDirection;
    position = direction === 1 ? 0 : duration;
    cycles = 0;
    render();
  }
  function restart() {
    reset();
    play();
  }
  function reverse() {
    direction *= -1;
    cycles = 0;
    previous = null;
    play();
  }
  function action(name) {
    if (name === "freeze") pause();
    else if (name === "reset") reset();
    else if (name === "restart") restart();
    else if (name === "reverse") reverse();
  }
  function enter() { play(); }
  function leave() { action(options.hover_out); }
  function click() {
    if (running || cycles > 0) action(options.click_again);
    else play();
  }
  function reducedMotion() {
    if (!media.matches) {
      for (const {node, parent} of animations) if (!node.parentNode) parent.appendChild(node);
      reset();
      if (options.trigger === "load") play();
      return;
    }
    reset();
    for (const {node} of animations) node.remove();
    svg.setCurrentTime(0);
  }
  const player = {
    play, pause, restart, reverse, reset,
    seek(time) {
      if (!Number.isFinite(time) || time < 0 || time > duration) throw new RangeError("time must be within the timeline");
      position = time;
      previous = null;
      render();
    },
    setSpeed(value) {
      if (!Number.isFinite(value) || value <= 0 || value > 100) throw new RangeError("speed must be between 0 and 100");
      speed = value;
      previous = null;
    },
    get currentTime() { return position; },
    get isPlaying() { return running; },
    get duration() { return duration; },
    destroy() {
      pause();
      destroyed = true;
      if (observer) observer.disconnect();
      svg.removeEventListener("mouseenter", enter);
      svg.removeEventListener("mouseleave", leave);
      svg.removeEventListener("click", click);
      media.removeEventListener("change", reducedMotion);
    }
  };
  svg.glaxnimatePlayer = player;
  media.addEventListener("change", reducedMotion);
  render();
  reducedMotion();
  if (options.trigger === "load") play();
  else if (options.trigger === "hover") {
    svg.addEventListener("mouseenter", enter);
    svg.addEventListener("mouseleave", leave);
  } else if (options.trigger === "click") svg.addEventListener("click", click);
  else if (options.trigger === "scroll") {
    const threshold = options.scroll_threshold / 100;
    observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting && entry.intersectionRatio >= threshold)) {
        play();
        observer.disconnect();
      }
    }, {threshold});
    observer.observe(svg);
  }
}());
