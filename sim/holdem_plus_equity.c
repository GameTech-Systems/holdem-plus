/* Hold'em Plus preflop equity simulator.
 * Monte Carlo all-in equity for all 169 starting hands, Texas Hold'em (best 5 of 7)
 * vs Hold'em Plus (third hole card, best 5 of 8), plus 14 three-card shapes.
 * Build:  gcc -O2 -o equity holdem_plus_equity.c -lm
 * Run:    ./equity [--hu-trials N] [--six-trials N] [--seed S] > results.json
 *         ./equity --cmp       (reads "n a1..an b1..bn" lines, prints -1/0/1; used by cross_check.py)
 *         ./equity --eval      (reads "n c1..cn" lines, prints the evaluator's rank code; used by exhaustive_check.py)
 *         ./equity --selftest  (exhaustive evaluator checks; exits 1 on any failure; ~20 seconds)
 * Options are validated: --seed must be a nonzero unsigned integer (xorshift is stuck at 0 forever),
 * trial counts must be integers >= 2 (needed for a standard error), unknown options are an error.
 * Cards are rank*4+suit, rank 0=2 .. 12=A, suit order c,d,h,s. See README.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <errno.h>
typedef uint64_t u64;
static u64 S=88172645463325252ULL,SEED0=88172645463325252ULL;
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
/* Standard error of the mean from running sums (s = sum x, s2 = sum x^2) over N samples. */
static double se_of(double s,double s2,long N){double m=s/N,v=(s2/N-m*m)*N/(N-1.0);return v>0?sqrt(v/N):0;}
/* se[0]=SE of Hold'em equity, se[1]=SE of Plus equity, se[2]=SE of the paired difference (Plus minus Hold'em),
   all as fractions of the pot (multiply by 100 for percentage points). */
static __attribute__((noinline)) void hand_eq(int h0,int h1,int op,long N,double*eh,double*ep,double*cs,long*cn,double*se){
 if(op<1||op>5){*eh=*ep=0;se[0]=se[1]=se[2]=0;return;} /* only 1 or 5 are ever passed; also tells the compiler the range of op */
 int d[50],m=0;for(int c=0;c<52;c++)if(c!=h0&&c!=h1)d[m++]=c;
 int k=3*op+6,suited=((h0&3)==(h1&3));double sh=0,sp=0,sh2=0,sp2=0,sd=0,sd2=0;
 for(long n=0;n<N;n++){
  for(int i=0;i<k;i++){int j=i+rnd()%(50-i);int t=d[i];d[i]=d[j];d[j]=t;}
  int*bd=d+2*op,third=d[2*op+5],c[8];uint32_t o7[5],o8[5];
  c[0]=h0;c[1]=h1;for(int i=0;i<5;i++)c[2+i]=bd[i];
  uint32_t m7=ev(c,7);c[7]=third;uint32_t m8=ev(c,8);
  for(int o=0;o<op;o++){int x[8];x[0]=d[2*o];x[1]=d[2*o+1];for(int i=0;i<5;i++)x[2+i]=bd[i];o7[o]=ev(x,7);x[7]=d[2*op+6+o];o8[o]=ev(x,8);}
  double s7=share(m7,o7,op),s8=share(m8,o8,op),df=s8-s7;
  sh+=s7;sh2+=s7*s7;sp+=s8;sp2+=s8*s8;sd+=df;sd2+=df*df;
  int tr=third>>2,cat=(tr==(h0>>2)||tr==(h1>>2))?0:((suited&&(third&3)==(h0&3))?1:2);
  cs[cat]+=s8;cn[cat]++;
 }
 *eh=sh/N;*ep=sp/N;se[0]=se_of(sh,sh2,N);se[1]=se_of(sp,sp2,N);se[2]=se_of(sd,sd2,N);
}
static double shape_eq(const int*x,int op,long N,double*se){
 int d[49],m=0;for(int c=0;c<52;c++){int u=0;for(int i=0;i<3;i++)if(x[i]==c)u=1;if(!u)d[m++]=c;}
 int k=3*op+5;double s=0,s2=0;
 for(long n=0;n<N;n++){
  for(int i=0;i<k;i++){int j=i+rnd()%(49-i);int t=d[i];d[i]=d[j];d[j]=t;}
  int*bd=d+3*op,c[8];uint32_t o[5];
  for(int i=0;i<3;i++)c[i]=x[i];
  for(int i=0;i<5;i++)c[3+i]=bd[i];
  uint32_t me=ev(c,8);
  for(int q=0;q<op;q++){int y[8];for(int i=0;i<3;i++)y[i]=d[3*q+i];for(int i=0;i<5;i++)y[3+i]=bd[i];o[q]=ev(y,8);}
  double v=share(me,o,op);s+=v;s2+=v*v;
 }
 *se=se_of(s,s2,N);return s/N;
}
static int pc(const char*s){const char*R="23456789TJQKA",*U="cdhs";int r=strchr(R,s[0])-R,u=strchr(U,s[1])-U;return r*4+u;}
static void cmp_mode(void){int n;while(scanf("%d",&n)==1){int a[8],b[8];for(int i=0;i<n;i++)(void)!scanf("%d",&a[i]);for(int i=0;i<n;i++)(void)!scanf("%d",&b[i]);uint32_t x=ev(a,n),y=ev(b,n);printf("%d\n",x>y?1:x<y?-1:0);}}

static void eval_mode(void){int n;while(scanf("%d",&n)==1){int a[8];for(int i=0;i<n;i++)(void)!scanf("%d",&a[i]);printf("%u\n",ev(a,n));}}

/* ---- exhaustive evaluator self-test ------------------------------------------------------------
 * 1. Every 5-card and every 7-card hand is enumerated and the category counts are compared with the
 *    classical exact values (2,598,960 and 133,784,560 hands). A single misclassified hand changes a count.
 * 2. For random 6-, 7- and 8-card hands, ev() must equal the maximum of ev() over all 5-card subsets, exactly.
 *    The 5-card path is validated by (1), so this checks the multi-card logic (two trips, three pairs, two
 *    quads, 6+ suited cards, ...) including the 8-card case that Hold'em Plus actually uses.
 * Category index = ev()>>20: 0 high card, 1 pair, 2 two pair, 3 trips, 4 straight, 5 flush, 6 full house,
 * 7 quads, 8 straight flush (royal included). */
static void enum_rec(int*c,int n,int depth,int start,long*cnt){
 if(depth==n){cnt[ev(c,n)>>20]++;return;}
 for(int x=start;x<=52-(n-depth);x++){c[depth]=x;enum_rec(c,n,depth+1,x+1,cnt);}
}
static int selftest(void){
 static const long K5[9]={1302540,1098240,123552,54912,10200,5108,3744,624,40};
 static const long K7[9]={23294460,58627800,31433400,6461620,6180020,4047644,3473184,224848,41584};
 static const char*nm[9]={"high card","pair","two pair","trips","straight","flush","full house","quads","straight flush"};
 int bad=0;
 for(int pass=0;pass<2;pass++){
  int n=pass?7:5;const long*K=pass?K7:K5;long cnt[9]={0},tot=0;int c[8];
  enum_rec(c,n,0,0,cnt);
  for(int i=0;i<9;i++){tot+=cnt[i];if(cnt[i]!=K[i]){bad++;printf("FAIL %d-card %-14s got %ld expected %ld\n",n,nm[i],cnt[i],K[i]);}}
  printf("%d-card exhaustive: %ld hands, %s\n",n,tot,bad?"MISMATCH":"all category counts exact");
 }
 S=0x9E3779B97F4A7C15ULL;
 for(int n=6;n<=8;n++){
  long trials=1000000,miss=0;
  for(long t=0;t<trials;t++){
   int d[52],c[8];for(int i=0;i<52;i++)d[i]=i;
   for(int i=0;i<n;i++){int j=i+rnd()%(52-i);int x=d[i];d[i]=d[j];d[j]=x;c[i]=d[i];}
   uint32_t full=ev(c,n),best=0;
   for(int m=0;m<(1<<n);m++){if(__builtin_popcount(m)!=5)continue;int s[5],q=0;for(int i=0;i<n;i++)if(m>>i&1)s[q++]=c[i];uint32_t v=ev(s,5);if(v>best)best=v;}
   if(full!=best){if(miss<3)printf("FAIL %d-card: ev=%u best-5-subset=%u\n",n,full,best);miss++;}
  }
  printf("%d-card best-of-subsets: %ld random hands, %ld mismatches\n",n,trials,miss);bad+=(miss>0);
 }
 printf(bad?"SELFTEST FAILED\n":"SELFTEST PASSED\n");return bad?1:0;
}
static long parse_trials(const char*flag,const char*s){
 char*e;errno=0;long v=strtol(s,&e,10);
 if(errno||e==s||*e||v<2){fprintf(stderr,"%s needs an integer >= 2, got '%s'\n",flag,s);exit(2);}
 return v;
}
static u64 parse_seed(const char*s){
 char*e;errno=0;u64 v=strtoull(s,&e,10);
 if(errno||e==s||*e||s[0]=='-'||v==0){fprintf(stderr,"--seed needs a nonzero unsigned integer (xorshift cannot run from 0), got '%s'\n",s);exit(2);}
 return v;
}
int main(int argc,char**argv){
 long NH=300000,NS=150000;
 for(int i=1;i<argc;i++){
  if(!strcmp(argv[i],"--cmp")){cmp_mode();return 0;}
  else if(!strcmp(argv[i],"--eval")){eval_mode();return 0;}
  else if(!strcmp(argv[i],"--selftest"))return selftest();
  else if(!strcmp(argv[i],"--hu-trials")&&i+1<argc)NH=parse_trials("--hu-trials",argv[++i]);
  else if(!strcmp(argv[i],"--six-trials")&&i+1<argc)NS=parse_trials("--six-trials",argv[++i]);
  else if(!strcmp(argv[i],"--seed")&&i+1<argc)SEED0=S=parse_seed(argv[++i]);
  else{fprintf(stderr,"usage: %s [--hu-trials N] [--six-trials N] [--seed S] | --cmp | --eval | --selftest\n",argv[0]);return 2;}
 }
 double H[2][169],P[2][169],C[3][169],E[3][2][169];int ops[2]={1,5};
 for(int v=0;v<2;v++){
  for(int i=0;i<13;i++)for(int j=0;j<13;j++){
   int a=12-i,b=12-j,h0,h1;
   if(i==j){h0=a*4;h1=a*4+1;}else if(i<j){h0=a*4;h1=b*4;}else{h0=b*4;h1=a*4+1;}
   double cs[3]={0},eh,ep,se[3];long cn[3]={0};
   hand_eq(h0,h1,ops[v],v?NS:NH,&eh,&ep,cs,cn,se);
   int id=i*13+j;H[v][id]=eh*100;P[v][id]=ep*100;
   for(int e=0;e<3;e++)E[e][v][id]=se[e]*100;
   for(int c=0;c<3;c++)C[c][id]=cn[c]?cs[c]/cn[c]*100:-1;
  }
 }
 printf("{\"hu\":{\"h\":");
 #define ARR(A) {printf("[");for(int i=0;i<169;i++){if(A[i]<0)printf("null");else printf("%.1f",A[i]);printf(i<168?",":"");}printf("]");}
 #define ARR3(A) {printf("[");for(int i=0;i<169;i++){printf("%.3f",A[i]);printf(i<168?",":"");}printf("]");}
 ARR(H[0]);printf(",\"p\":");ARR(P[0]);printf(",\"pr\":");ARR(C[0]);printf(",\"su\":");ARR(C[1]);printf(",\"mi\":");ARR(C[2]);
 printf("},\"six\":{\"h\":");ARR(H[1]);printf(",\"p\":");ARR(P[1]);printf("},\"sh\":[");
 const char*nm[]={"Trips","Aces + king","Nines + ace kicker","Nines + low kicker","Fives + junk","Ace-high, three suited","King-queen-jack, three suited","9-8-7, three suited","J-10-9, rainbow","Ace-king suited + low off","Ace-king-queen, rainbow","Ace + two low, rainbow","Jack-10 suited + low off","Rainbow junk"};
 const char*ex[]={"7s7h7d","AsAhKd","9s9hAd","9s9h4d","5s5h9d","As9s4s","KsQsJs","9s8s7s","JsTh9d","AsKs4d","AsKhQd","As8h3d","JsTs4d","9s5h2d"};
 for(int s=0;s<14;s++){int x[3]={pc(ex[s]),pc(ex[s]+2),pc(ex[s]+4)};
  /* Two separate statements, six-handed first: the RNG stream is shared, so the order matters. The original
     code made both calls inside one printf(), whose argument evaluation order C leaves unspecified (gcc happens
     to go right to left). Fixing it here keeps the published numbers and makes them compiler-independent. */
  double se6,se1,e6=shape_eq(x,5,NS,&se6),e1=shape_eq(x,1,NH,&se1);
  printf("[\"%s\",\"%s\",%.1f,%.1f,%.3f,%.3f]%s",nm[s],ex[s],e1*100,e6*100,se1*100,se6*100,s<13?",":"");}
 printf("],\"se\":{\"hu\":{\"h\":");ARR3(E[0][0]);printf(",\"p\":");ARR3(E[1][0]);printf(",\"d\":");ARR3(E[2][0]);
 printf("},\"six\":{\"h\":");ARR3(E[0][1]);printf(",\"p\":");ARR3(E[1][1]);printf(",\"d\":");ARR3(E[2][1]);
 printf("}},\"meta\":{\"seed\":\"%llu\",\"hu_trials\":%ld,\"six_trials\":%ld,\"se_units\":\"percentage points (1 standard error)\"}}\n",
        (unsigned long long)SEED0,NH,NS);
 return 0;}
