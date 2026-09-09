import metadata from '@/data/security-metadata.json';
import type {Dataset,Position} from '@/lib/domain';

const curatedTickers=metadata.tickers as Record<string,string>;
const unlisted=metadata.unlisted as Record<string,string>;

export function resolvedTicker(position:Pick<Position,'cusip'|'ticker'>){
 return position.ticker||curatedTickers[position.cusip]||null;
}

export function securityLabel(position:Pick<Position,'cusip'|'ticker'|'name'>){
 return resolvedTicker(position)||unlisted[position.cusip]||position.name;
}

export function withSecurityMetadata(dataset:Dataset):Dataset{
 const known=new Map<string,string>();
 for(const fund of dataset.funds)for(const snapshot of fund.snapshots)for(const position of snapshot.positions){
  const ticker=resolvedTicker(position);if(ticker)known.set(position.cusip,ticker);
 }
 return {...dataset,funds:dataset.funds.map(fund=>({...fund,snapshots:fund.snapshots.map(snapshot=>({...snapshot,positions:snapshot.positions.map(position=>{
  const ticker=position.ticker||known.get(position.cusip)||curatedTickers[position.cusip];
  return ticker&&!position.ticker?{...position,ticker}:position;
 })}))}))};
}
