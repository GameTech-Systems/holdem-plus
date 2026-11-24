/* Hold'em Plus preflop equity simulator.
 * Monte Carlo all-in equity for all 169 starting hands, Texas Hold'em (best 5 of 7)
 * vs Hold'em Plus (third hole card, best 5 of 8), plus 14 three-card shapes.
 * Build:  gcc -O2 -o equity holdem_plus_equity.c
 * Run:    ./equity [--hu-trials N] [--six-trials N] [--seed S] > results.json
 *         ./equity --cmp   (reads "n a1..an b1..bn" lines, prints -1/0/1; used by cross_check.py)
 * Cards are rank*4+suit, rank 0=2 .. 12=A, suit order c,d,h,s. See README.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
typedef uint64_t u64;
static u64 S=88172645463325252ULL;
static inline u64 rnd(){S^=S<<13;S^=S>>7;S^=S<<17;return S;}
static inline int shigh(int m){int w=(m<<1)|((m>>12)&1);for(int t=13;t>=4;t--)if(((w>>(t-4))&31)==31)return t;return 0;}
static inline uint32_t topk(int m,int k){uint32_t v=0;for(int r=12;r>=0&&k>0;r--)if((m>>r)&1){v=(v<<4)|(r+1);k--;}while(k-->0)v<<=4;return v;}
static uint32_t ev(const int*c,int n){
 int rc[13]={0},sm[4]={0},sc[4]={0},rm=0,fm=0;
 for(int i=0;i<n;i++){int r=c[i]>>2,s=c[i]&3;rc[r]++;sm[s]|=1<<r;sc[s]++;rm|=1<<r;}
 for(int s=0;s<4;s++)if(sc[s]>=5){fm=sm[s];int t=shigh(fm);if(t)return (8u<<20)|t;}
 int q=-1,t3[2]={-1,-1},nt=0,p[4],np=0;
 for(int r=12;r>=0;r--){if(rc[r]==4&&q<0)q=r;else if(rc[r]==3){if(nt<2)t3[nt++]=r;}else if(rc[r]==2){if(np<4)p[np++]=r;}}
 if(q>=0)return (7u<<20)|((q+1)<<4)|topk(rm&~(1<<q),1);
 if(nt>=1&&(nt>=2||np>=1)){int pr=-1;if(nt>=2)pr=t3[1];if(np&&p[0]>pr)pr=p[0];return (6u<<20)|((t3[0]+1)<<4)|(pr+1);}
 if(fm)return (5u<<20)|topk(fm,5);
 int t=shigh(rm);if(t)return (4u<<20)|t;
 if(nt>=1)return (3u<<20)|((t3[0]+1)<<8)|topk(rm&~(1<<t3[0]),2);
 if(np>=2)return (2u<<20)|((p[0]+1)<<8)|((p[1]+1)<<4)|topk(rm&~((1<<p[0])|(1<<p[1])),1);
 if(np==1)return (1u<<20)|((p[0]+1)<<12)|topk(rm&~(1<<p[0]),3);
 return topk(rm,5);
}
static inline double share(uint32_t me,const uint32_t*o,int n){int ties=0;for(int i=0;i<n;i++){if(o[i]>me)return 0;if(o[i]==me)ties++;}return 1.0/(1+ties);}
static void hand_eq(int h0,int h1,int op,long N,double*eh,double*ep,double*cs,long*cn){
 int d[50],m=0;for(int c=0;c<52;c++)if(c!=h0&&c!=h1)d[m++]=c;
 int k=3*op+6,suited=((h0&3)==(h1&3));double sh=0,sp=0;
 for(long n=0;n<N;n++){
  for(int i=0;i<k;i++){int j=i+rnd()%(50-i);int t=d[i];d[i]=d[j];d[j]=t;}
  int*bd=d+2*op,third=d[2*op+5],c[8];uint32_t o7[5],o8[5];
  c[0]=h0;c[1]=h1;for(int i=0;i<5;i++)c[2+i]=bd[i];
  uint32_t m7=ev(c,7);c[7]=third;uint32_t m8=ev(c,8);
  for(int o=0;o<op;o++){int x[8];x[0]=d[2*o];x[1]=d[2*o+1];for(int i=0;i<5;i++)x[2+i]=bd[i];o7[o]=ev(x,7);x[7]=d[2*op+6+o];o8[o]=ev(x,8);}
  sh+=share(m7,o7,op);double s8=share(m8,o8,op);sp+=s8;
  int tr=third>>2,cat=(tr==(h0>>2)||tr==(h1>>2))?0:((suited&&(third&3)==(h0&3))?1:2);
  cs[cat]+=s8;cn[cat]++;
 }
 *eh=sh/N;*ep=sp/N;
}
static double shape_eq(const int*x,int op,long N){
 int d[49],m=0;for(int c=0;c<52;c++){int u=0;for(int i=0;i<3;i++)if(x[i]==c)u=1;if(!u)d[m++]=c;}
 int k=3*op+5;double s=0;
 for(long n=0;n<N;n++){
  for(int i=0;i<k;i++){int j=i+rnd()%(49-i);int t=d[i];d[i]=d[j];d[j]=t;}
  int*bd=d+3*op,c[8];uint32_t o[5];
  for(int i=0;i<3;i++)c[i]=x[i];
  for(int i=0;i<5;i++)c[3+i]=bd[i];
  uint32_t me=ev(c,8);
  for(int q=0;q<op;q++){int y[8];for(int i=0;i<3;i++)y[i]=d[3*q+i];for(int i=0;i<5;i++)y[3+i]=bd[i];o[q]=ev(y,8);}
  s+=share(me,o,op);
 }
 return s/N;
}
static int pc(const char*s){const char*R="23456789TJQKA",*U="cdhs";int r=strchr(R,s[0])-R,u=strchr(U,s[1])-U;return r*4+u;}
static void cmp_mode(void){int n;while(scanf("%d",&n)==1){int a[8],b[8];for(int i=0;i<n;i++)(void)!scanf("%d",&a[i]);for(int i=0;i<n;i++)(void)!scanf("%d",&b[i]);uint32_t x=ev(a,n),y=ev(b,n);printf("%d\n",x>y?1:x<y?-1:0);}}
int main(int argc,char**argv){
 long NH=300000,NS=150000;
 for(int i=1;i<argc;i++){
  if(!strcmp(argv[i],"--cmp")){cmp_mode();return 0;}
  else if(!strcmp(argv[i],"--hu-trials")&&i+1<argc)NH=atol(argv[++i]);
  else if(!strcmp(argv[i],"--six-trials")&&i+1<argc)NS=atol(argv[++i]);
  else if(!strcmp(argv[i],"--seed")&&i+1<argc)S=strtoull(argv[++i],0,10);
 }
 double H[2][169],P[2][169],C[3][169];int ops[2]={1,5};
 for(int v=0;v<2;v++){
  for(int i=0;i<13;i++)for(int j=0;j<13;j++){
   int a=12-i,b=12-j,h0,h1;
   if(i==j){h0=a*4;h1=a*4+1;}else if(i<j){h0=a*4;h1=b*4;}else{h0=b*4;h1=a*4+1;}
   double cs[3]={0},eh,ep;long cn[3]={0};
   hand_eq(h0,h1,ops[v],v?NS:NH,&eh,&ep,cs,cn);
   int id=i*13+j;H[v][id]=eh*100;P[v][id]=ep*100;
   for(int c=0;c<3;c++)C[c][id]=cn[c]?cs[c]/cn[c]*100:-1;
  }
 }
 printf("{\"hu\":{\"h\":");
 #define ARR(A) {printf("[");for(int i=0;i<169;i++){if(A[i]<0)printf("null");else printf("%.1f",A[i]);printf(i<168?",":"");}printf("]");}
 ARR(H[0]);printf(",\"p\":");ARR(P[0]);printf(",\"pr\":");ARR(C[0]);printf(",\"su\":");ARR(C[1]);printf(",\"mi\":");ARR(C[2]);
 printf("},\"six\":{\"h\":");ARR(H[1]);printf(",\"p\":");ARR(P[1]);printf("},\"sh\":[");
 const char*nm[]={"Trips","Aces + king","Nines + ace kicker","Nines + low kicker","Fives + junk","Ace-high, three suited","King-queen-jack, three suited","9-8-7, three suited","J-10-9, rainbow","Ace-king suited + low off","Ace-king-queen, rainbow","Ace + two low, rainbow","Jack-10 suited + low off","Rainbow junk"};
 const char*ex[]={"7s7h7d","AsAhKd","9s9hAd","9s9h4d","5s5h9d","As9s4s","KsQsJs","9s8s7s","JsTh9d","AsKs4d","AsKhQd","As8h3d","JsTs4d","9s5h2d"};
 for(int s=0;s<14;s++){int x[3]={pc(ex[s]),pc(ex[s]+2),pc(ex[s]+4)};
  printf("[\"%s\",\"%s\",%.1f,%.1f]%s",nm[s],ex[s],shape_eq(x,1,NH)*100,shape_eq(x,5,NS)*100,s<13?",":"");}
 printf("]}\n");return 0;}
