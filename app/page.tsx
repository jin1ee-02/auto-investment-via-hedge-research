import Dashboard from '@/components/hedge-dashboard';
import data from '@/data/bootstrap.json';
import type { Dataset } from '@/lib/domain';
export default function Home(){return <Dashboard initialData={data as Dataset}/>}
