/** Straight-line kilometres: two decimals under 10 km, one above. */
export const km = (value: number) => `${value.toFixed(value < 10 ? 2 : 1)} km`
