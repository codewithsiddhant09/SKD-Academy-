'use client';

import { ChangeEvent, FormEvent, useMemo, useState } from 'react';

type BookingFields = {
  customer_name: string;
  phone: string;
  salon: string;
  service: string;
  date: string;
  time: string;
};

const fieldConfig = [
  { label: 'Customer Name', name: 'customer_name', type: 'text', placeholder: 'Sara Khan' },
  { label: 'Phone Number', name: 'phone', type: 'tel', placeholder: '+971501234567' },
  { label: 'Selected Salon', name: 'salon', type: 'text', placeholder: 'Marina Luxe Salon' },
  { label: 'Selected Service', name: 'service', type: 'text', placeholder: 'Hair Smoothing' },
  { label: 'Date', name: 'date', type: 'date', placeholder: '' },
  { label: 'Time', name: 'time', type: 'time', placeholder: '' },
] as const;

export function BookingPanel({ fields }: { fields: string[] }) {
  const sessionId = useMemo(() => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return `booking-${Math.random().toString(36).slice(2)}`;
  }, []);

  const [formData, setFormData] = useState<BookingFields>({
    customer_name: '',
    phone: '',
    salon: '',
    service: '',
    date: '',
    time: '',
  });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState<{ booking_id: string; status: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const { name, value } = event.target;
    setFormData((current) => ({ ...current, [name]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch('/book-appointment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, ...formData }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || 'Unable to confirm booking');
      }

      const data = await response.json();
      setSuccess({ booking_id: data.booking_id, status: data.status });
      setFormData({ customer_name: '', phone: '', salon: '', service: '', date: '', time: '' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error occurred');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-[32px] border border-white/80 bg-white/90 p-6 shadow-soft">
      <div className="mb-5">
        <h3 className="text-lg font-semibold text-text">Booking Panel</h3>
        <p className="mt-1 text-sm text-text/70">Use the form to validate appointment details and submit a booking request.</p>
      </div>

      <form onSubmit={handleSubmit} className="grid gap-4">
        {fieldConfig.map((field) => (
          <label key={field.name} className="grid gap-2 text-sm text-text/80">
            <span className="font-medium text-text">{field.label}</span>
            <input
              type={field.type}
              name={field.name}
              value={formData[field.name]}
              onChange={handleChange}
              placeholder={field.placeholder}
              className="w-full rounded-3xl border border-secondary/20 bg-secondary/5 px-4 py-3 text-sm text-text outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/10"
            />
          </label>
        ))}

        {error ? <p className="rounded-3xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
        {success ? (
          <div className="rounded-3xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-900">
            <p className="font-semibold">Booking confirmed</p>
            <p className="mt-1">ID: {success.booking_id}</p>
            <p className="mt-1">Status: {success.status}</p>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 rounded-3xl bg-primary px-4 py-3 text-sm font-semibold text-white transition hover:bg-primary/95 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {loading ? 'Confirming…' : 'Confirm Appointment'}
        </button>
      </form>
    </div>
  );
}
