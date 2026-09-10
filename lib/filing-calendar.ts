export const filingCalendarSource='https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f';
// SEC FAQ Q25 calendar, including weekend and federal-holiday adjustments.
const deadlines:Record<string,string>={
 '2026-03-31':'2026-05-15','2026-06-30':'2026-08-14','2026-09-30':'2026-11-16','2026-12-31':'2027-02-16',
 '2027-03-31':'2027-05-17','2027-06-30':'2027-08-16','2027-09-30':'2027-11-15','2027-12-31':'2028-02-14',
};
export function filingCalendar(period:string){
 const date=new Date(period+'T00:00:00Z');
 if(!/^\d{4}-(03-31|06-30|09-30|12-31)$/.test(period)||!Number.isFinite(date.getTime()))throw Error('Invalid filing quarter');
 const quarter=Math.floor(date.getUTCMonth()/3)+1;
 const nextPeriod=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+4,0)).toISOString().slice(0,10);
 return {label:`${date.getUTCFullYear()}년 ${quarter}분기`,nextLabel:`${quarter===4?date.getUTCFullYear()+1:date.getUTCFullYear()}년 ${quarter===4?1:quarter+1}분기`,nextPeriod,deadline:deadlines[nextPeriod]||null};
}
