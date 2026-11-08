
#include <stdio.h>
#include <nds32_isr.h>
#include <nds32_intrinsic.h>
#include "CH568SFR.H"
#include "MYdebug.H"

void __c_init(void);
int main(void);

void NDS32ATTR_RESET("vectors=16") reset_handler(void)
{
	__c_init();
	main();
}

void __c_init(void)
{

#define MEMCPY(des, src, n) __builtin_memcpy ((des), (src), (n))
#define MEMSET(s, c, n) __builtin_memset ((s), (c), (n))

	extern char _end;
	extern char __bss_start;
	int size;
	extern char __data_lmastart;
	extern char __data_start;
	extern char _edata;


	size = &_edata - &__data_start;
	MEMCPY(&__data_start, &__data_lmastart, size);


	size = &_end - &__bss_start;
	MEMSET(&__bss_start, 0, size);
	return;
}

void Interrupt_init(UINT16 itnum)
{
	__nds32__mtsr(itnum, NDS32_SR_INT_MASK2);
	__nds32__setgie_en();
	__nds32__dsb();
}


void mInitSTDIO_UR3 (void)
{
	UINT32	x;

	R8_UART3_DIV = 1;
	x = 10 * FREQ_SYS / R8_UART3_DIV * 2 / 16 / STDIO_BAUD_RATE;
	x = ( x + 5 ) / 10;
	R16_UART3_DL = x;
	R8_UART3_FCR = RB_FCR_FIFO_TRIG | RB_FCR_TX_FIFO_CLR | RB_FCR_RX_FIFO_CLR | RB_FCR_FIFO_EN;
	R8_UART3_LCR = RB_LCR_WORD_SZ;
	R8_UART3_IER = RB_IER_TXD_EN;
	R32_PA_PU |= bRXD3 | bTXD3;
	R32_PA_DIR |= bTXD3;


	printf("ch5%02x mailbox debug\n", R8_CHIP_ID);
}


#undef putchar
int putchar( int c )
{
	while	( R8_UART3_TFC == UART_FIFO_SIZE );
	R8_UART3_THR = c;
	return c;
}
__attribute__((used))
void nds_write(const unsigned char *buf, int size)
{
	int i;
	for(i=0; i<size; i++)
		putchar(buf[i]);
}


void PowerInit(void)
{

	R8_SAFE_ACCESS_SIG = 0x57;
	R8_SAFE_ACCESS_SIG = 0xa8;

	R8_SLP_POWER_CTRL = 0;

}


void SysClkInit(void)
{

	R8_SAFE_ACCESS_SIG = 0x57;
	R8_SAFE_ACCESS_SIG = 0xa8;
	R8_CLK_PLL_DIV = 0x40 | 0x05;
	R8_CLK_CFG_CTRL = 0x80 | RB_CLK_SEL_PLL ;


	mDelayuS(2);

	PowerInit();
}


void	mDelayuS( UINT16 n )
{
	R32_TMR1_CNT_END = FREQ_SYS/1000000*n-15;
	R8_TMR1_INT_FLAG |= RB_TMR_IF_CYC_END;
	R8_TMR1_CTRL_MOD = RB_TMR_ALL_CLEAR ;

	R8_TMR1_CTRL_MOD = RB_TMR_COUNT_EN;
	while(!(R8_TMR1_INT_FLAG & RB_TMR_IF_CYC_END));
	R8_TMR1_CTRL_MOD = 0;
}


void	mDelaymS( UINT16 n )
{
	while ( n ) {
		mDelayuS( 1000 );
		-- n;
	}
}


