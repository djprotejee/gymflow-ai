// Shared formatting keeps forecast and planner screens speaking the same language.
export function prettyModelName(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatSlot(value: string) {
  return new Date(value).toLocaleString("en-US", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatForecastSlot(value: string) {
  return new Date(value).toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatPredictionSlot(value: string) {
  const date = new Date(value);
  const rounded = new Date(date);
  const minutes = rounded.getMinutes();
  if (minutes < 15) {
    rounded.setMinutes(0, 0, 0);
  } else if (minutes < 45) {
    rounded.setMinutes(30, 0, 0);
  } else {
    rounded.setHours(rounded.getHours() + 1, 0, 0, 0);
  }
  return rounded.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatTrainingWindow(value: string, minutes = 90) {
  const start = new Date(value);
  const roundedStart = new Date(start);
  const roundedMinutes = roundedStart.getMinutes();
  if (roundedMinutes <= 15) {
    roundedStart.setMinutes(0, 0, 0);
  } else if (roundedMinutes <= 45) {
    roundedStart.setMinutes(30, 0, 0);
  } else {
    roundedStart.setHours(roundedStart.getHours() + 1, 0, 0, 0);
  }
  const end = new Date(roundedStart.getTime() + minutes * 60 * 1000);
  const date = start.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  const startTime = roundedStart.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  const endTime = end.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${startTime}-${endTime}`;
}

export function toDateTimeLocalValue(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value.replace(" ", "T").slice(0, 16);
  }
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 16);
}
