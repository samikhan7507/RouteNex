import React, { useState } from 'react';
import { CreditCard, ShieldCheck, FlaskConical } from 'lucide-react';
import { api, money, uuid } from '../api';
import { useApp } from '../store';
import { Button, ErrorBox, Modal } from './ui';

function loadRazorpay() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve();
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = resolve; script.onerror = () => reject(new Error('Could not load the payment provider. Check your connection and retry.'));
    document.head.appendChild(script);
  });
}

export default function PaymentModal({ checkout, onClose, onSuccess }) {
  const { user, toast } = useApp();
  const [busy, setBusy] = useState(false), [error, setError] = useState(null);
  const demo = checkout.provider === 'demo';
  const finishDemo = async outcome => {
    setBusy(true); setError(null);
    try {
      const result = await api(`/payments/${checkout.id}/demo`, { method: 'POST', body: { outcome } });
      if (outcome === 'success') { toast('Test payment captured — no real money was moved'); onSuccess?.(result); onClose(); }
      else { toast('Test payment failed; reservation released', 'error'); onSuccess?.(result); onClose(); }
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const payReal = async () => {
    setBusy(true); setError(null);
    try {
      await loadRazorpay();
      const rz = new window.Razorpay({
        key: checkout.key_id, amount: checkout.amount_paise, currency: 'INR', name: 'RouteNex',
        description: `${checkout.purpose.replace('_', ' ')} ${checkout.reference_id || ''}`.trim(),
        order_id: checkout.provider_order_id, prefill: { name: user.name, email: user.email || '', contact: user.phone || '' },
        theme: { color: '#17456b' },
        handler: async response => {
          try {
            const result = await api('/payments/verify', { method: 'POST', body: response });
            toast('Payment verified'); onSuccess?.(result); onClose();
          } catch (e) { setError(e); toast('Verification pending. Check payment history before retrying.', 'error'); }
        },
        modal: { ondismiss: () => { setBusy(false); setError(new Error('Checkout was closed. If money was debited, check payment history; the provider webhook will reconcile it.')); } },
      });
      rz.on('payment.failed', response => { setError(new Error(response.error?.description || 'Payment failed')); setBusy(false); });
      rz.open();
    } catch (e) { setError(e); setBusy(false); }
  };
  return <Modal title={demo ? 'Test payment' : 'Secure payment'} onClose={onClose}>
    <div className="payment-summary">
      {demo ? <FlaskConical size={28} /> : <CreditCard size={28} />}
      <div><strong>{money(checkout.amount)}</strong><span>{checkout.purpose.replaceAll('_', ' ')} · {checkout.receipt}</span></div>
    </div>
    {demo ? <div className="notice warn"><strong>Demo mode — no real charge.</strong><p>This simulates a UPI/card payment so you can test the full order lifecycle. Production uses Razorpay Checkout and server-side verification.</p></div>
      : <div className="notice"><ShieldCheck size={17} /><p>Card details are entered only in Razorpay's secure checkout. RouteNex verifies the payment on the server before confirming your purchase.</p></div>}
    <ErrorBox error={error} />
    <div className="modal-actions">
      <Button variant="secondary" onClick={onClose} disabled={busy}>Close</Button>
      {demo ? <><Button variant="danger" loading={busy} onClick={() => finishDemo('failure')}>Simulate failure</Button><Button loading={busy} onClick={() => finishDemo('success')}>Simulate success</Button></>
        : <Button loading={busy} onClick={payReal}>Pay {money(checkout.amount)}</Button>}
    </div>
  </Modal>;
}

export async function createCheckout(purpose, referenceId, amount) {
  return api('/payments/checkout', { method: 'POST', body: { purpose, reference_id: referenceId, amount, idempotency_key: uuid() } });
}
