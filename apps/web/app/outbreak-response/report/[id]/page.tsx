import { notFound } from 'next/navigation';
import LguReport from '@/components/lgu-report';
import './report.css';

export const metadata = { title: 'Dengue bed capacity briefing | SurgeWise' };

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[a-f0-9]{64}$/.test(id)) notFound();
  return <LguReport key={id} id={id} />;
}
