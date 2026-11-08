
#ifndef __WCH_DEGBU_H__
#define __WCH_DEGBU_H__

#ifdef __cplusplus
extern "C" {
#endif

#define STR(S)		#S
#define XSTR(S)		STR(S)

#define	STDIO_BAUD_RATE		115200

extern void SysClkInit(void);
extern void mInitSTDIO_UR3 (void);

extern void	mDelayuS( UINT16 n );
extern void	mDelaymS( UINT16 n );

extern void Interrupt_init(UINT16 itnum);

#ifdef __cplusplus
}
#endif

#endif
