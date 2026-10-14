import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Truck } from 'lucide-react';
import { api, Facility } from './api';

export default function ReplenishmentApprovals() {
  const qc = useQueryClient();
  const requests = useQuery({ queryKey: ['requests'], queryFn: () => api.get('/replenishments').then(r => r.data) });
  const facilities = useQuery({ queryKey: ['facilities'], queryFn: () => api.get('/facilities').then(r => r.data) });
  const [message, setMessage] = useState('');

  async function update(id: number, action: string, body: Record<string, unknown> = {}) {
    try {
      await api.post(`/replenishments/${id}/${action}`, body);
      setMessage(`Request updated: ${action.replace('_', ' ')}.`);
      await qc.invalidateQueries({ queryKey: ['requests'] });
      await qc.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'Action could not be completed.');
    }
  }

  function receive(request: any) {
    const facility = facilities.data?.find((item: Facility) => item.id === request.facility_id);
    const batch = facility?.batches.find((item: Facility['batches'][number]) => item.verified && item.expiry && new Date(item.expiry) > new Date());
    if (!batch) {
      setMessage('No verified, in-date batch is available at the destination. Register or verify a batch first.');
      return;
    }
    const quantity = window.prompt(`Quantity received (up to ${request.outstanding})`);
    if (!quantity) return;
    update(request.id, 'receive', { quantity: Number(quantity), batch_id: batch.id });
  }

  function verify(request: any) {
    const facility = facilities.data?.find((item: Facility) => item.id === request.facility_id);
    const batch = facility?.batches.find((item: Facility['batches'][number]) => item.verified && item.expiry && new Date(item.expiry) > new Date());
    if (!batch) {
      setMessage('No verified, in-date batch is available at the destination. Register or verify a batch first.');
      return;
    }
    update(request.id, 'verify', { batch_id: batch.id, reason: 'Physical count verified after delivery' });
  }

  const active = (requests.data || []).filter((request: any) => !['verified', 'rejected'].includes(request.status));

  return <section className="panel table-panel" id="request-approvals">
    <div className="panel-header"><div><h3><Check size={15} /> Worker replenishment requests</h3><p>Review worker requests, then record dispatch, delivery, and ASV vial verification here.</p></div><span className="status-pill pending">{active.length} active</span></div>
    {message && <div className="success-banner dismissable">{message}<button type="button" aria-label="Dismiss message" onClick={() => setMessage('')}>×</button></div>}
    {requests.isLoading || facilities.isLoading ? <div className="loading">Loading worker requests…</div> : requests.isError || facilities.isError ? <div className="error-state">Unable to load replenishment requests. Refresh and try again.</div> : active.length ? <div className="table-wrap"><table><thead><tr><th>Request</th><th>Facility</th><th>Quantity</th><th>Priority</th><th>Status</th><th>Expected</th><th>Officer action</th></tr></thead><tbody>
      {active.map((request: any) => <tr key={request.id}>
        <td><b>{request.request_code}</b><small>{request.created_at ? new Date(request.created_at).toLocaleDateString() : ''}</small></td>
        <td>{request.facility}<small>{request.facility_name}</small></td>
        <td><b>{request.received}/{request.quantity}</b><small>{request.outstanding} remaining</small></td>
        <td><span className={'priority ' + request.priority}>{request.priority}</span></td>
        <td><span className={'status-pill ' + request.status}>{request.status.replace('_', ' ')}</span></td>
        <td>{request.expected_date || '—'}</td>
        <td><div className="row-actions">
          {request.status === 'pending' && <><button className="tiny-action approve" onClick={() => update(request.id, 'approve')}>Approve</button><button className="tiny-action reject" onClick={() => { const reason = window.prompt('Reason for returning this request'); if (reason) update(request.id, 'reject', { reason }); }}>Return for review</button></>}
          {request.status === 'approved' && <button className="tiny-action approve" onClick={() => update(request.id, 'dispatch')}>Record dispatch</button>}
          {['dispatched', 'partially_received'].includes(request.status) && <button className="tiny-action" onClick={() => receive(request)}><Truck size={13} /> Record delivery</button>}
          {request.status === 'received' && <button className="tiny-action approve" onClick={() => verify(request)}>Verify received ASV vials</button>}
        </div></td>
      </tr>)}
    </tbody></table></div> : <div className="empty-state">No worker requests need action. New requests from facilities will appear here.</div>}
  </section>;
}
