import { redirect } from 'next/navigation';

export default function ForecastRedirect() {
  redirect('/outbreak-response?mode=future');
}
