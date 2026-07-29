export function formatCurrency(value) { return `$${Number(value || 0).toFixed(2)}`; }
export function formatDate(value) { return new Date(value).toLocaleDateString(); }
