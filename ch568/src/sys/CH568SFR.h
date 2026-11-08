

#ifndef __BASE_TYPE__
#define __BASE_TYPE__

#ifdef __cplusplus
extern "C" {
#endif


#ifndef TRUE
#define TRUE                    1
#define FALSE                   0
#endif
#ifndef NULL
#define NULL                    0
#endif

#ifndef VOID
#define VOID                    void
#endif
#ifndef CONST
#define CONST                   const
#endif
#ifndef BOOL
typedef unsigned char           BOOL;
#endif
#ifndef BOOLEAN
typedef unsigned char           BOOLEAN;
#endif
#ifndef CHAR
typedef char                    CHAR;
#endif
#ifndef INT8
typedef char                    INT8;
#endif
#ifndef INT16
typedef short                   INT16;
#endif
#ifndef INT32
typedef long                    INT32;
#endif
#ifndef UINT8
typedef unsigned char           UINT8;
#endif
#ifndef UINT16
typedef unsigned short          UINT16;
#endif
#ifndef UINT32
typedef unsigned long           UINT32;
#endif
#ifndef UINT8V
typedef unsigned char volatile  UINT8V;
#endif
#ifndef UINT16V
typedef unsigned short volatile UINT16V;
#endif
#ifndef UINT32V
typedef unsigned long volatile  UINT32V;
#endif

#ifndef PVOID
typedef void                    *PVOID;
#endif
#ifndef PCHAR
typedef char                    *PCHAR;
#endif
#ifndef PCHAR
typedef const char              *PCCHAR;
#endif
#ifndef PINT8
typedef char                    *PINT8;
#endif
#ifndef PINT16
typedef short                   *PINT16;
#endif
#ifndef PINT32
typedef long                    *PINT32;
#endif
#ifndef PUINT8
typedef unsigned char           *PUINT8;
#endif
#ifndef PUINT16
typedef unsigned short          *PUINT16;
#endif
#ifndef PUINT32
typedef unsigned long           *PUINT32;
#endif
#ifndef PUINT8V
typedef volatile unsigned char  *PUINT8V;
#endif
#ifndef PUINT16V
typedef volatile unsigned short *PUINT16V;
#endif
#ifndef PUINT32V
typedef volatile unsigned long  *PUINT32V;
#endif


#define	FREQ_SYS			96000000

#ifndef min
#define min(a,b)                (((a) < (b)) ? (a) : (b))
#endif
#ifndef max
#define max(a,b)                (((a) > (b)) ? (a) : (b))
#endif

#if		DEBUG
#define PRINT(X...) printf(X)
#else
#define PRINT(X...)
#endif


#define FIELD_OFFSET(Type, Field)    ((UINT16)&(((Type *)0)->Field))


#define FIELD_SIZE(Type, Field)      (sizeof(((Type *)0)->Field))


#define FIELD_TYPE(Type, Field)      (((Type *)0)->Field)


#define NUMBER_OF(Array)             (sizeof(Array)/sizeof((Array)[0]))
#define NUMBER_OF_FIELD(Type, Field) (NUMBER_OF(FIELD_TYPE(Type, Field)))

#ifdef __cplusplus
}
#endif

#endif


#ifndef __CH568GPSFR_H__
#define __CH568GPSFR_H__

#ifdef __cplusplus
extern "C" {
#endif


#define R32_SAFE_ACCESS     (*((PUINT32V)0x00401000))
#define R8_SAFE_ACCESS_SIG  (*((PUINT8V)0x00401000))
#define  RB_SAFE_ACC_MODE   0x03
#define  RB_SAFE_ACC_TIMER  0x70
#define R8_CHIP_ID          (*((PUINT8V)0x00401001))
#define R8_SAFE_ACCESS_ID   (*((PUINT8V)0x00401002))


#define R32_GLOBAL_CONFIG   (*((PUINT32V)0x00401004))
#define R8_GLOB_ROM_CFG     (*((PUINT8V)0x00401004))
#define  RB_ROM_EXT_RE      0x01
#define  RB_CODE_RAM_WE     0x02
#define  RB_ROM_DATA_WE     0x04
#define  RB_ROM_CODE_WE     0x08

#define R8_RST_BOOT_STAT    (*((PUINT8V)0x00401005))
#define  RB_RESET_FLAG      0x03
#define  RST_FLAG_SW        0x00
#define  RST_FLAG_POR       0x01
#define  RST_FLAG_PIN       0x03


#define  RB_CFG_RESET_EN    0x04
#define  RB_CFG_BOOT_EN     0x08
#define  RB_CFG_DEBUG_EN    0x10
#define  RB_BOOT_LOADER     0x20
#define R8_RST_WDOG_CTRL    (*((PUINT8V)0x00401006))
#define  RB_SOFTWARE_RESET  0x01
#define R8_GLOB_RESET_KEEP  (*((PUINT8V)0x00401007))


#define R32_CLOCK_CONFIG    (*((PUINT32V)0x00401008))
#define R8_CLK_PLL_DIV      (*((PUINT8V)0x00401008))
#define R8_CLK_CFG_CTRL     (*((PUINT8V)0x0040100A))
#define  RB_CLK_PLL_SLEEP   0x01
#define  RB_CLK_SEL_PLL     0x02


#define R32_SLEEP_CONTROL   (*((PUINT32V)0x0040100C))
#define R8_SLP_CLK_OFF0     (*((PUINT8V)0x0040100C))
#define  RB_SLP_CLK_TMR0    0x01
#define  RB_SLP_CLK_TMR1    0x02
#define  RB_SLP_CLK_TMR2    0x04
#define  RB_SLP_CLK_PWMX    0x08
#define  RB_SLP_CLK_UART0   0x10
#define  RB_SLP_CLK_UART1   0x20
#define  RB_SLP_CLK_UART2   0x40
#define  RB_SLP_CLK_UART3   0x80
#define R8_SLP_CLK_OFF1     (*((PUINT8V)0x0040100D))
#define  RB_SLP_CLK_SPI0    0x01
#define  RB_SLP_CLK_SPI1    0x02
#define  RB_SLP_CLK_SDC     0x04
#define  RB_SLP_CLK_LED     0x08
#define  RB_SLP_CLK_USB0    0x10
#define  RB_SLP_CLK_USB1    0x20
#define  RB_SLP_CLK_SATA    0x40
#define  RB_SLP_CLK_ECDC    0x80
#define R8_SLP_WAKE_CTRL    (*((PUINT8V)0x0040100E))
#define  RB_SLP_USB0_WAKE   0x01
#define  RB_SLP_USB1_WAKE   0x02
#define  RB_SLP_SATA_WAKE   0x04
#define  RB_SLP_GPIO_WAKE   0x10
#define R8_SLP_POWER_CTRL   (*((PUINT8V)0x0040100F))
#define  RB_SLP_USB0_PWRDN  0x01
#define  RB_SLP_USB1_PWRDN  0x02
#define  RB_SLP_SATA_PWRDN  0x04
#define  RB_SLP_STANDBY     0x80


#define R32_PORT_CONFIG     (*((PUINT32V)0x00401010))
#define R8_XBUS_CONFIG      (*((PUINT8V)0x00401010))
#define  RB_XBUS_ENABLE     0x01
#define  RB_XBUS_ADDR_OE    0x0C
#define  RB_XBUS_WIDTH      0x30
#define  RB_XBUS_HOLD       0x40
#define  RB_XBUS_SETUP      0x80
#define R8_PORT_PIN         (*((PUINT8V)0x00401012))
#define  RB_PIN_TMR1        0x02
#define  RB_PIN_TMR2        0x04
#define  RB_PIN_UART0       0x10
#define  RB_PIN_UART1       0x20


#define R32_GPIO_INT_CTRL   (*((PUINT32V)0x0040101C))
#define R8_GPIO_INT_STATUS  (*((PUINT8V)0x0040101C))
#define R8_GPIO_INT_ENABLE  (*((PUINT8V)0x0040101D))
#define R8_GPIO_INT_MODE    (*((PUINT8V)0x0040101E))
#define R8_GPIO_INT_POLAR   (*((PUINT8V)0x0040101F))


#define BA_GPIO_INT_CTRL    ((PUINT8V)0x0040101C)
#define GPIO_INT_STATUS     0x00
#define GPIO_INT_ENABLE     0x01
#define GPIO_INT_MODE       0x02
#define GPIO_INT_POLAR      0x03
#define  RB_GPIO_PA3        0x01
#define  RB_GPIO_PA4        0x02
#define  RB_GPIO_PA6        0x04
#define  RB_GPIO_PA10       0x08
#define  RB_GPIO_PA11       0x10
#define  RB_GPIO_PA12       0x20
#define  RB_GPIO_PB4        0x40
#define  RB_GPIO_PB10       0x80


#define R32_PA_DIR          (*((PUINT32V)0x00401040))
#define R8_PA_DIR_0         (*((PUINT8V)0x00401040))
#define R8_PA_DIR_1         (*((PUINT8V)0x00401041))
#define R32_PA_PIN          (*((PUINT32V)0x00401044))
#define R8_PA_PIN_0         (*((PUINT8V)0x00401044))
#define R8_PA_PIN_1         (*((PUINT8V)0x00401045))
#define R32_PA_OUT          (*((PUINT32V)0x00401048))
#define R8_PA_OUT_0         (*((PUINT8V)0x00401048))
#define R8_PA_OUT_1         (*((PUINT8V)0x00401049))
#define R32_PA_CLR          (*((PUINT32V)0x0040104C))
#define R8_PA_CLR_0         (*((PUINT8V)0x0040104C))
#define R8_PA_CLR_1         (*((PUINT8V)0x0040104D))
#define R32_PA_PU           (*((PUINT32V)0x00401050))
#define R8_PA_PU_0          (*((PUINT8V)0x00401050))
#define R8_PA_PU_1          (*((PUINT8V)0x00401051))
#define R32_PA_PD           (*((PUINT32V)0x00401054))
#define R8_PA_PD_0          (*((PUINT8V)0x00401054))
#define R8_PA_PD_1          (*((PUINT8V)0x00401055))
#define R32_PA_DRV          (*((PUINT32V)0x00401058))
#define R8_PA_DRV_0         (*((PUINT8V)0x00401058))
#define R8_PA_DRV_1         (*((PUINT8V)0x00401059))
#define R32_PA_SMT          (*((PUINT32V)0x0040105C))
#define R8_PA_SMT_0         (*((PUINT8V)0x0040105C))
#define R8_PA_SMT_1         (*((PUINT8V)0x0040105D))


#define R32_PB_DIR          (*((PUINT32V)0x00401060))
#define R8_PB_DIR_0         (*((PUINT8V)0x00401060))
#define R8_PB_DIR_1         (*((PUINT8V)0x00401061))
#define R32_PB_PIN          (*((PUINT32V)0x00401064))
#define R8_PB_PIN_0         (*((PUINT8V)0x00401064))
#define R8_PB_PIN_1         (*((PUINT8V)0x00401065))
#define R32_PB_OUT          (*((PUINT32V)0x00401068))
#define R8_PB_OUT_0         (*((PUINT8V)0x00401068))
#define R8_PB_OUT_1         (*((PUINT8V)0x00401069))
#define R32_PB_CLR          (*((PUINT32V)0x0040106C))
#define R8_PB_CLR_0         (*((PUINT8V)0x0040106C))
#define R8_PB_CLR_1         (*((PUINT8V)0x0040106D))
#define R32_PB_PU           (*((PUINT32V)0x00401070))
#define R8_PB_PU_0          (*((PUINT8V)0x00401070))
#define R8_PB_PU_1          (*((PUINT8V)0x00401071))
#define R32_PB_PD           (*((PUINT32V)0x00401074))
#define R8_PB_PD_0          (*((PUINT8V)0x00401074))
#define R8_PB_PD_1          (*((PUINT8V)0x00401075))
#define R32_PB_DRV          (*((PUINT32V)0x00401078))
#define R8_PB_DRV_0         (*((PUINT8V)0x00401078))
#define R8_PB_DRV_1         (*((PUINT8V)0x00401079))
#define R32_PB_SMT          (*((PUINT32V)0x0040107C))
#define R8_PB_SMT_0         (*((PUINT8V)0x0040107C))
#define R8_PB_SMT_1         (*((PUINT8V)0x0040107D))


#define BA_PA               ((PUINT8V)0x00401040)
#define BA_PB               ((PUINT8V)0x00401060)
#define GPIO_DIR            0x00
#define GPIO_DIR_0          0x00
#define GPIO_DIR_1          0x01
#define GPIO_PIN            0x04
#define GPIO_PIN_0          0x04
#define GPIO_PIN_1          0x05
#define GPIO_OUT            0x08
#define GPIO_OUT_0          0x08
#define GPIO_OUT_1          0x09
#define GPIO_CLR            0x0C
#define GPIO_CLR_0          0x0C
#define GPIO_CLR_1          0x0D
#define GPIO_PU             0x10
#define GPIO_PU_0           0x10
#define GPIO_PU_1           0x11
#define GPIO_PD             0x14
#define GPIO_PD_0           0x14
#define GPIO_PD_1           0x15
#define GPIO_DRV            0x18
#define GPIO_DRV_0          0x18
#define GPIO_DRV_1          0x19
#define GPIO_SMT            0x1C
#define GPIO_SMT_0          0x1C
#define GPIO_SMT_1          0x1D


#define  bSCK1              (1<<0)
#define  bLED0              (1<<0)
#define  bCMD1              (1<<0)
#define  bSDO               (1<<1)
#define  bMOSI1             bSDO
#define  bLED1              (1<<1)
#define  bCMD2              (1<<1)
#define  bSDI               (1<<2)
#define  bMISO1             bSDI
#define  bLED2              (1<<2)
#define  bCMD3              (1<<2)
#define  bINT0              (1<<3)
#define  bTMR0              (1<<3)
#define  bCAP0              bTMR0
#define  bPWM4              bTMR0
#define  bLED3              (1<<3)
#define  bINT1              (1<<4)
#define  bRXD3              (1<<4)
#define  bPWM0              (1<<4)
#define  bLEDC              (1<<4)
#define  bTXD3              (1<<5)
#define  bPWM1              (1<<5)
#define  bINT2              (1<<6)
#define  bRXD2              (1<<6)
#define  bSDCK              (1<<6)
#define  bTXD2              (1<<7)
#define  bCMD0              (1<<7)
#define  bRXD1              (1<<8)
#define  bPWM2              (1<<8)
#define  bSD00              (1<<8)
#define  bTXD1              (1<<9)
#define  bPWM3              (1<<9)
#define  bSD01              (1<<9)
#define  bINT3              (1<<10)
#define  bTMR1              (1<<10)
#define  bCAP1              bTMR1
#define  bPWM5              bTMR1
#define  bSD02              (1<<10)
#define  bINT4              (1<<11)
#define  bTMR2              (1<<11)
#define  bCAP2              bTMR2
#define  bPWM6              bTMR2
#define  bSD03              (1<<11)
#define  bINT5              (1<<12)
#define  bSCS               (1<<12)
#define  bSD10              (1<<12)
#define  bSCK0              (1<<13)
#define  bSD11              (1<<13)
#define  bMOSI              (1<<14)
#define  bTXD0_             (1<<14)
#define  bSD12              (1<<14)
#define  bMISO              (1<<15)
#define  bRXD0_             (1<<15)
#define  bSD13              (1<<15)
#define  bED0BUS            (0xFF<<8)
#define  bCTS               (1<<0)
#define  bSD20              (1<<0)
#define  bDSR               (1<<1)
#define  bSD21              (1<<1)
#define  bTMR1_             (1<<2)
#define  bCAP1_             bTMR1_
#define  bPWM5_             bTMR1_
#define  bRI                (1<<2)
#define  bSD22              (1<<2)
#define  bDCD               (1<<3)
#define  bSD23              (1<<3)
#define  bINT6              (1<<4)
#define  bRXD0              (1<<4)
#define  bSD30              (1<<4)
#define  bDTR               (1<<5)
#define  bSD31              (1<<5)
#define  bRTS               (1<<6)
#define  bSD32              (1<<6)
#define  bTXD0              (1<<7)
#define  bSD33              (1<<7)
#define  bED1BUS            (0xFF<<0)
#define  bRXD1_             (1<<8)
#define  bRD                (1<<8)
#define  bTXD1_             (1<<9)
#define  bWR                (1<<9)
#define  bINT7              (1<<10)
#define  bTIO               (1<<10)
#define  bTMR2_             (1<<11)
#define  bCAP2_             bTMR2_
#define  bPWM6_             bTMR2_
#define  bA14               (1<<11)
#define  bA12               (1<<12)
#define  bA13               (1<<13)
#define  bTCK               (1<<15)
#define  bRST               (1<<15)


#define R32_TMR0_CONTROL    (*((PUINT32V)0x00402000))
#define R8_TMR0_CTRL_MOD    (*((PUINT8V)0x00402000))
#define R8_TMR0_INTER_EN    (*((PUINT8V)0x00402002))
#define R32_TMR0_STATUS     (*((PUINT32V)0x00402004))
#define R8_TMR0_INT_FLAG    (*((PUINT8V)0x00402006))
#define R8_TMR0_FIFO_COUNT  (*((PUINT8V)0x00402007))
#define R32_TMR0_COUNT      (*((PUINT32V)0x00402008))
#define R16_TMR0_COUNT      (*((PUINT16V)0x00402008))
#define R8_TMR0_COUNT       (*((PUINT8V)0x00402008))
#define R32_TMR0_CNT_END    (*((PUINT32V)0x0040200C))
#define R32_TMR0_FIFO       (*((PUINT32V)0x00402010))
#define R16_TMR0_FIFO       (*((PUINT16V)0x00402010))
#define R8_TMR0_FIFO        (*((PUINT8V)0x00402010))


#define R32_TMR1_CONTROL    (*((PUINT32V)0x00402400))
#define R8_TMR1_CTRL_MOD    (*((PUINT8V)0x00402400))
#define R8_TMR1_CTRL_DMA    (*((PUINT8V)0x00402401))
#define R8_TMR1_INTER_EN    (*((PUINT8V)0x00402402))
#define R32_TMR1_STATUS     (*((PUINT32V)0x00402404))
#define R8_TMR1_INT_FLAG    (*((PUINT8V)0x00402406))
#define R8_TMR1_FIFO_COUNT  (*((PUINT8V)0x00402407))
#define R32_TMR1_COUNT      (*((PUINT32V)0x00402408))
#define R16_TMR1_COUNT      (*((PUINT16V)0x00402408))
#define R8_TMR1_COUNT       (*((PUINT8V)0x00402408))
#define R32_TMR1_CNT_END    (*((PUINT32V)0x0040240C))
#define R32_TMR1_FIFO       (*((PUINT32V)0x00402410))
#define R16_TMR1_FIFO       (*((PUINT16V)0x00402410))
#define R8_TMR1_FIFO        (*((PUINT8V)0x00402410))
#define R32_TMR1_DMA_NOW    (*((PUINT32V)0x00402414))
#define R16_TMR1_DMA_NOW    (*((PUINT16V)0x00402414))
#define R32_TMR1_DMA_BEG    (*((PUINT32V)0x00402418))
#define R16_TMR1_DMA_BEG    (*((PUINT16V)0x00402418))
#define R32_TMR1_DMA_END    (*((PUINT32V)0x0040241C))
#define R16_TMR1_DMA_END    (*((PUINT16V)0x0040241C))


#define R32_TMR2_CONTROL    (*((PUINT32V)0x00402800))
#define R8_TMR2_CTRL_MOD    (*((PUINT8V)0x00402800))
#define R8_TMR2_CTRL_DMA    (*((PUINT8V)0x00402801))
#define R8_TMR2_INTER_EN    (*((PUINT8V)0x00402802))
#define R32_TMR2_STATUS     (*((PUINT32V)0x00402804))
#define R8_TMR2_INT_FLAG    (*((PUINT8V)0x00402806))
#define R8_TMR2_FIFO_COUNT  (*((PUINT8V)0x00402807))
#define R32_TMR2_COUNT      (*((PUINT32V)0x00402808))
#define R16_TMR2_COUNT      (*((PUINT16V)0x00402808))
#define R8_TMR2_COUNT       (*((PUINT8V)0x00402808))
#define R32_TMR2_CNT_END    (*((PUINT32V)0x0040280C))
#define R32_TMR2_FIFO       (*((PUINT32V)0x00402810))
#define R16_TMR2_FIFO       (*((PUINT16V)0x00402810))
#define R8_TMR2_FIFO        (*((PUINT8V)0x00402810))
#define R32_TMR2_DMA_NOW    (*((PUINT32V)0x00402814))
#define R16_TMR2_DMA_NOW    (*((PUINT16V)0x00402814))
#define R32_TMR2_DMA_BEG    (*((PUINT32V)0x00402818))
#define R16_TMR2_DMA_BEG    (*((PUINT16V)0x00402818))
#define R32_TMR2_DMA_END    (*((PUINT32V)0x0040281C))
#define R16_TMR2_DMA_END    (*((PUINT16V)0x0040281C))


#define TMR_FIFO_SIZE       8
#define BA_TMR0             ((PUINT8V)0x00402000)
#define BA_TMR1             ((PUINT8V)0x00402400)
#define BA_TMR2             ((PUINT8V)0x00402800)
#define TMR_CTRL_MOD        0
#define  RB_TMR_MODE_IN     0x01
#define  RB_TMR_ALL_CLEAR   0x02
#define  RB_TMR_COUNT_EN    0x04
#define  RB_TMR_OUT_EN      0x08
#define  RB_TMR_OUT_POLAR   0x10
#define  RB_TMR_CAP_COUNT   0x10
#define  RB_TMR_PWM_REPEAT  0xC0
#define  RB_TMR_CAP_EDGE    0xC0
#define TMR_CTRL_DMA        1
#define  RB_TMR_DMA_ENABLE  0x01
#define  RB_TMR_DMA_LOOP    0x04
#define TMR_INTER_EN        2
#define  RB_TMR_IE_CYC_END  0x01
#define  RB_TMR_IE_DATA_ACT 0x02
#define  RB_TMR_IE_FIFO_HF  0x04
#define  RB_TMR_IE_DMA_END  0x08
#define  RB_TMR_IE_FIFO_OV  0x10
#define TMR_INT_FLAG        6
#define  RB_TMR_IF_CYC_END  0x01
#define  RB_TMR_IF_DATA_ACT 0x02
#define  RB_TMR_IF_FIFO_HF  0x04
#define  RB_TMR_IF_DMA_END  0x08
#define  RB_TMR_IF_FIFO_OV  0x10
#define TMR_FIFO_COUNT      7
#define TMR_COUNT           0x08
#define TMR_CNT_END         0x0C
#define TMR_FIFO            0x10
#define TMR_DMA_NOW         0x14
#define TMR_DMA_BEG         0x18
#define TMR_DMA_END         0x1C


#define R32_UART0_CTRL      (*((PUINT32V)0x00403000))
#define R8_UART0_MCR        (*((PUINT8V)0x00403000))
#define R8_UART0_IER        (*((PUINT8V)0x00403001))
#define R8_UART0_FCR        (*((PUINT8V)0x00403002))
#define R8_UART0_LCR        (*((PUINT8V)0x00403003))
#define R32_UART0_STAT      (*((PUINT32V)0x00403004))
#define R8_UART0_IIR        (*((PUINT8V)0x00403004))
#define R8_UART0_LSR        (*((PUINT8V)0x00403005))
#define R8_UART0_MSR        (*((PUINT8V)0x00403006))
#define R32_UART0_FIFO      (*((PUINT32V)0x00403008))
#define R8_UART0_RBR        (*((PUINT8V)0x00403008))
#define R8_UART0_THR        (*((PUINT8V)0x00403008))
#define R8_UART0_RFC        (*((PUINT8V)0x0040300A))
#define R8_UART0_TFC        (*((PUINT8V)0x0040300B))
#define R32_UART0_SETUP     (*((PUINT32V)0x0040300C))
#define R16_UART0_DL        (*((PUINT16V)0x0040300C))
#define R8_UART0_DLL        (*((PUINT8V)0x0040300C))
#define R8_UART0_DLM        (*((PUINT8V)0x0040300D))
#define R8_UART0_DIV        (*((PUINT8V)0x0040300E))
#define R8_UART0_ADR        (*((PUINT8V)0x0040300F))


#define R32_UART1_CTRL      (*((PUINT32V)0x00403400))
#define R8_UART1_MCR        (*((PUINT8V)0x00403400))
#define R8_UART1_IER        (*((PUINT8V)0x00403401))
#define R8_UART1_FCR        (*((PUINT8V)0x00403402))
#define R8_UART1_LCR        (*((PUINT8V)0x00403403))
#define R32_UART1_STAT      (*((PUINT32V)0x00403404))
#define R8_UART1_IIR        (*((PUINT8V)0x00403404))
#define R8_UART1_LSR        (*((PUINT8V)0x00403405))
#define R32_UART1_FIFO      (*((PUINT32V)0x00403408))
#define R8_UART1_RBR        (*((PUINT8V)0x00403408))
#define R8_UART1_THR        (*((PUINT8V)0x00403408))
#define R8_UART1_RFC        (*((PUINT8V)0x0040340A))
#define R8_UART1_TFC        (*((PUINT8V)0x0040340B))
#define R32_UART1_SETUP     (*((PUINT32V)0x0040340C))
#define R16_UART1_DL        (*((PUINT16V)0x0040340C))
#define R8_UART1_DLL        (*((PUINT8V)0x0040340C))
#define R8_UART1_DLM        (*((PUINT8V)0x0040340D))
#define R8_UART1_DIV        (*((PUINT8V)0x0040340E))


#define R32_UART2_CTRL      (*((PUINT32V)0x00403800))
#define R8_UART2_MCR        (*((PUINT8V)0x00403800))
#define R8_UART2_IER        (*((PUINT8V)0x00403801))
#define R8_UART2_FCR        (*((PUINT8V)0x00403802))
#define R8_UART2_LCR        (*((PUINT8V)0x00403803))
#define R32_UART2_STAT      (*((PUINT32V)0x00403804))
#define R8_UART2_IIR        (*((PUINT8V)0x00403804))
#define R8_UART2_LSR        (*((PUINT8V)0x00403805))
#define R32_UART2_FIFO      (*((PUINT32V)0x00403808))
#define R8_UART2_RBR        (*((PUINT8V)0x00403808))
#define R8_UART2_THR        (*((PUINT8V)0x00403808))
#define R8_UART2_RFC        (*((PUINT8V)0x0040380A))
#define R8_UART2_TFC        (*((PUINT8V)0x0040380B))
#define R32_UART2_SETUP     (*((PUINT32V)0x0040380C))
#define R16_UART2_DL        (*((PUINT16V)0x0040380C))
#define R8_UART2_DLL        (*((PUINT8V)0x0040380C))
#define R8_UART2_DLM        (*((PUINT8V)0x0040380D))
#define R8_UART2_DIV        (*((PUINT8V)0x0040380E))


#define R32_UART3_CTRL      (*((PUINT32V)0x00403C00))
#define R8_UART3_MCR        (*((PUINT8V)0x00403C00))
#define R8_UART3_IER        (*((PUINT8V)0x00403C01))
#define R8_UART3_FCR        (*((PUINT8V)0x00403C02))
#define R8_UART3_LCR        (*((PUINT8V)0x00403C03))
#define R32_UART3_STAT      (*((PUINT32V)0x00403C04))
#define R8_UART3_IIR        (*((PUINT8V)0x00403C04))
#define R8_UART3_LSR        (*((PUINT8V)0x00403C05))
#define R32_UART3_FIFO      (*((PUINT32V)0x00403C08))
#define R8_UART3_RBR        (*((PUINT8V)0x00403C08))
#define R8_UART3_THR        (*((PUINT8V)0x00403C08))
#define R8_UART3_RFC        (*((PUINT8V)0x00403C0A))
#define R8_UART3_TFC        (*((PUINT8V)0x00403C0B))
#define R32_UART3_SETUP     (*((PUINT32V)0x00403C0C))
#define R16_UART3_DL        (*((PUINT16V)0x00403C0C))
#define R8_UART3_DLL        (*((PUINT8V)0x00403C0C))
#define R8_UART3_DLM        (*((PUINT8V)0x00403C0D))
#define R8_UART3_DIV        (*((PUINT8V)0x00403C0E))


#define UART_FIFO_SIZE      8
#define UART_RECV_RDY_SZ    7
#define BA_UART0            ((PUINT8V)0x00403000)
#define BA_UART1            ((PUINT8V)0x00403400)
#define BA_UART2            ((PUINT8V)0x00403800)
#define BA_UART3            ((PUINT8V)0x00403C00)
#define UART_MCR            0
#define  RB_MCR_DTR         0x01
#define  RB_MCR_RTS         0x02
#define  RB_MCR_OUT1        0x04
#define  RB_MCR_OUT2        0x08
#define  RB_MCR_INT_OE      0x08
#define  RB_MCR_LOOP        0x10
#define  RB_MCR_AU_FLOW_EN  0x20
#define  RB_MCR_TNOW        0x40
#define  RB_MCR_HALF        0x80
#define UART_IER            1
#define  RB_IER_RECV_RDY    0x01
#define  RB_IER_THR_EMPTY   0x02
#define  RB_IER_LINE_STAT   0x04
#define  RB_IER_MODEM_CHG   0x08
#define  RB_IER_DTR_EN      0x10
#define  RB_IER_RTS_EN      0x20
#define  RB_IER_TXD_EN      0x40
#define  RB_IER_RESET       0x80
#define UART_FCR            2
#define  RB_FCR_FIFO_EN     0x01
#define  RB_FCR_RX_FIFO_CLR 0x02
#define  RB_FCR_TX_FIFO_CLR 0x04
#define  RB_FCR_FIFO_TRIG   0xC0
#define UART_LCR            3
#define  RB_LCR_WORD_SZ     0x03
#define  RB_LCR_STOP_BIT    0x04
#define  RB_LCR_PAR_EN      0x08
#define  RB_LCR_PAR_MOD     0x30
#define  RB_LCR_BREAK_EN    0x40
#define  RB_LCR_DLAB        0x80
#define  RB_LCR_GP_BIT      0x80
#define UART_IIR            4
#define  RB_IIR_NO_INT      0x01
#define  RB_IIR_INT_MASK    0x0F
#define  RB_IIR_FIFO_ID     0xC0
#define UART_LSR            5
#define  RB_LSR_DATA_RDY    0x01
#define  RB_LSR_OVER_ERR    0x02
#define  RB_LSR_PAR_ERR     0x04
#define  RB_LSR_FRAME_ERR   0x08
#define  RB_LSR_BREAK_ERR   0x10
#define  RB_LSR_TX_FIFO_EMP 0x20
#define  RB_LSR_TX_ALL_EMP  0x40
#define  RB_LSR_ERR_RX_FIFO 0x80
#define UART_MSR            6
#define  RB_MSR_CTS_CHG     0x01
#define  RB_MSR_DSR_CHG     0x02
#define  RB_MSR_RI_CHG      0x04
#define  RB_MSR_DCD_CHG     0x08
#define  RB_MSR_CTS         0x10
#define  RB_MSR_DSR         0x20
#define  RB_MSR_RI          0x40
#define  RB_MSR_DCD         0x80
#define UART_RBR            8
#define UART_THR            8
#define UART_RFC            0x0A
#define UART_TFC            0x0B
#define UART_DLL            0x0C
#define UART_DLM            0x0D
#define UART_DIV            0x0E
#define UART_ADR            0x0F


#define UART_II_SLV_ADDR    0x0E
#define UART_II_LINE_STAT   0x06
#define UART_II_RECV_RDY    0x04
#define UART_II_RECV_TOUT   0x0C
#define UART_II_THR_EMPTY   0x02
#define UART_II_MODEM_CHG   0x00
#define UART_II_NO_INTER    0x01


#define R32_SPI0_CONTROL    (*((PUINT32V)0x00404000))
#define R8_SPI0_CTRL_MOD    (*((PUINT8V)0x00404000))
#define R8_SPI0_CTRL_CFG    (*((PUINT8V)0x00404001))
#define R8_SPI0_INTER_EN    (*((PUINT8V)0x00404002))
#define R8_SPI0_CLOCK_DIV   (*((PUINT8V)0x00404003))
#define R8_SPI0_SLAVE_PRE   (*((PUINT8V)0x00404003))
#define R32_SPI0_STATUS     (*((PUINT32V)0x00404004))
#define R8_SPI0_BUFFER      (*((PUINT8V)0x00404004))
#define R8_SPI0_RUN_FLAG    (*((PUINT8V)0x00404005))
#define R8_SPI0_INT_FLAG    (*((PUINT8V)0x00404006))
#define R8_SPI0_FIFO_COUNT  (*((PUINT8V)0x00404007))
#define R32_SPI0_TOTAL_CNT  (*((PUINT32V)0x0040400C))
#define R16_SPI0_TOTAL_CNT  (*((PUINT16V)0x0040400C))
#define R32_SPI0_FIFO       (*((PUINT32V)0x00404010))
#define R8_SPI0_FIFO        (*((PUINT8V)0x00404010))
#define R8_SPI0_FIFO_COUNT1 (*((PUINT8V)0x00404013))
#define R32_SPI0_DMA_NOW    (*((PUINT32V)0x00404014))
#define R16_SPI0_DMA_NOW    (*((PUINT16V)0x00404014))
#define R32_SPI0_DMA_BEG    (*((PUINT32V)0x00404018))
#define R16_SPI0_DMA_BEG    (*((PUINT16V)0x00404018))
#define R32_SPI0_DMA_END    (*((PUINT32V)0x0040401C))
#define R16_SPI0_DMA_END    (*((PUINT16V)0x0040401C))


#define R32_SPI1_CONTROL    (*((PUINT32V)0x00404400))
#define R8_SPI1_CTRL_MOD    (*((PUINT8V)0x00404400))
#define R8_SPI1_CTRL_CFG    (*((PUINT8V)0x00404401))
#define R8_SPI1_INTER_EN    (*((PUINT8V)0x00404402))
#define R8_SPI1_CLOCK_DIV   (*((PUINT8V)0x00404403))
#define R32_SPI1_STATUS     (*((PUINT32V)0x00404404))
#define R8_SPI1_BUFFER      (*((PUINT8V)0x00404404))
#define R8_SPI1_RUN_FLAG    (*((PUINT8V)0x00404405))
#define R8_SPI1_INT_FLAG    (*((PUINT8V)0x00404406))
#define R8_SPI1_FIFO_COUNT  (*((PUINT8V)0x00404407))
#define R32_SPI1_TOTAL_CNT  (*((PUINT32V)0x0040440C))
#define R16_SPI1_TOTAL_CNT  (*((PUINT16V)0x0040440C))
#define R32_SPI1_FIFO       (*((PUINT32V)0x00404410))
#define R8_SPI1_FIFO        (*((PUINT8V)0x00404410))
#define R8_SPI1_FIFO_COUNT1 (*((PUINT8V)0x00404413))


#define SPI_FIFO_SIZE       8
#define BA_SPI0             ((PUINT8V)0x00404000)
#define BA_SPI1             ((PUINT8V)0x00404400)
#define SPI_CTRL_MOD        0
#define  RB_SPI_MODE_SLAVE  0x01
#define  RB_SPI_ALL_CLEAR   0x02
#define  RB_SPI_2WIRE_MOD   0x04
#define  RB_SPI_MST_SCK_MOD 0x08
#define  RB_SPI_SLV_CMD_MOD 0x08
#define  RB_SPI_FIFO_DIR    0x10
#define  RB_SPI_SCK_OE      0x20
#define  RB_SPI_MOSI_OE     0x40
#define  RB_SPI1_SDO_OE     0x40
#define  RB_SPI_MISO_OE     0x80
#define  RB_SPI1_SDI_OE     0x80
#define SPI_CTRL_CFG        1
#define  RB_SPI_DMA_ENABLE  0x01
#define  RB_SPI_DMA_LOOP    0x04
#define  RB_SPI_AUTO_IF     0x10
#define  RB_SPI_BIT_ORDER   0x20
#define SPI_INTER_EN        2
#define  RB_SPI_IE_CNT_END  0x01
#define  RB_SPI_IE_BYTE_END 0x02
#define  RB_SPI_IE_FIFO_HF  0x04
#define  RB_SPI_IE_DMA_END  0x08
#define  RB_SPI_IE_FIFO_OV  0x10
#define  RB_SPI_IE_FST_BYTE 0x80
#define SPI_CLOCK_DIV       3
#define SPI_SLAVE_PRESET    3
#define SPI_BUFFER          4
#define SPI_RUN_FLAG        5
#define  RB_SPI_SLV_CMD_ACT 0x10
#define  RB_SPI_FIFO_READY  0x20
#define  RB_SPI_SLV_CS_LOAD 0x40
#define  RB_SPI_SLV_SELECT  0x80
#define SPI_INT_FLAG        6
#define  RB_SPI_IF_CNT_END  0x01
#define  RB_SPI_IF_BYTE_END 0x02
#define  RB_SPI_IF_FIFO_HF  0x04
#define  RB_SPI_IF_DMA_END  0x08
#define  RB_SPI_IF_FIFO_OV  0x10
#define  RB_SPI_FREE        0x40
#define  RB_SPI_IF_FST_BYTE 0x80
#define SPI_FIFO_COUNT      7
#define SPI_TOTAL_CNT       0x0C
#define SPI_FIFO            0x10
#define SPI_DMA_NOW         0x14
#define SPI_DMA_BEG         0x18
#define SPI_DMA_END         0x1C


#define R32_PWM_CONTROL     (*((PUINT32V)0x00405000))
#define R8_PWM_CTRL_MOD     (*((PUINT8V)0x00405000))
#define R8_PWM_CTRL_CFG     (*((PUINT8V)0x00405001))
#define R8_PWM_CLOCK_DIV    (*((PUINT8V)0x00405002))
#define R32_PWM_DATA        (*((PUINT32V)0x00405004))
#define R8_PWM0_DATA        (*((PUINT8V)0x00405004))
#define R8_PWM1_DATA        (*((PUINT8V)0x00405005))
#define R8_PWM2_DATA        (*((PUINT8V)0x00405006))
#define R8_PWM3_DATA        (*((PUINT8V)0x00405007))


#define BA_PWMX             ((PUINT8V)0x00405000)
#define PWM_CTRL_MOD        0
#define  RB_PWM0_OUT_EN     0x01
#define  RB_PWM1_OUT_EN     0x02
#define  RB_PWM2_OUT_EN     0x04
#define  RB_PWM3_OUT_EN     0x08
#define  RB_PWM0_POLAR      0x10
#define  RB_PWM1_POLAR      0x20
#define  RB_PWM2_POLAR      0x40
#define  RB_PWM3_POLAR      0x80
#define PWM_CTRL_CFG        1
#define  RB_PWM_CYCLE_SEL   0x01
#define PWM_CLOCK_DIV       2
#define PWM0_DATA_HOLD      4
#define PWM1_DATA_HOLD      5
#define PWM2_DATA_HOLD      6
#define PWM3_DATA_HOLD      7


#define R32_LED_CONTROL     (*((PUINT32V)0x00406000))
#define R8_LED_CTRL_MOD     (*((PUINT8V)0x00406000))
#define R8_LED_CLOCK_DIV    (*((PUINT8V)0x00406001))
#define R8_LED_STATUS       (*((PUINT8V)0x00406004))
#define R32_LED_FIFO        (*((PUINT32V)0x00406008))
#define R16_LED_FIFO        (*((PUINT16V)0x00406008))
#define R32_LED_DMA_CNT     (*((PUINT32V)0x00406010))
#define R16_LED_DMA_CNT     (*((PUINT16V)0x00406010))
#define R32_LED_DMA_MAIN    (*((PUINT32V)0x00406014))
#define R16_LED_DMA_MAIN    (*((PUINT16V)0x00406014))
#define R32_LED_DMA_AUX     (*((PUINT32V)0x00406018))
#define R16_LED_DMA_AUX     (*((PUINT16V)0x00406018))


#define LED_FIFO_SIZE       2
#define BA_LED              ((PUINT8V)0x00406000)
#define LED_CTRL_MOD        0
#define  RB_LED_BIT_ORDER   0x01
#define  RB_LED_ALL_CLEAR   0x02
#define  RB_LED_OUT_POLAR   0x04
#define  RB_LED_OUT_EN      0x08
#define  RB_LED_DMA_EN      0x10
#define  RB_LED_IE_FIFO     0x20
#define  RB_LED_CHAN_MOD    0xC0


#define LED_CLOCK_DIV       1
#define LED_STATUS          4
#define  RB_LED_FIFO_COUNT  0x07
#define  RB_LED_CLOCK       0x10
#define  RB_LED_IF_FIFO     0x20
#define  RB_LED_FIFO_EMPTY  0x40
#define  RB_LED_IF_DMA_END  0x80
#define LED_FIFO            8
#define LED_DMA_CNT         0x10
#define LED_DMA_BEG         0x14
#define LED_DMA_END         0x18


#define BA_CODE             ((PUINT32)0x00000000)
#define SZ_CODE             0x00080000
#define BA_SFR              ((PUINT32)0x00400000)
#define SZ_SFR              0x00010000
#define BA_RAM              ((PUINT32)0x00200000)
#define SZ_RAM              0x00008000
#define BA_XBUS             ((PUINT32)0x00800000)
#define SZ_XBUS             0x00008000


#define ID_CH568            0x68
#define ID_CH567            0x67
#define ID_CH566            0x66
#define ID_CH565            0x65


#define INT_ID_SW           NDS32_INT_H0
#define INT_ID_TMR0         NDS32_INT_H1
#define INT_ID_GPIO         NDS32_INT_H2
#define INT_ID_SPI0         NDS32_INT_H3
#define INT_ID_SATA         NDS32_INT_H4
#define INT_ID_USB0         NDS32_INT_H4
#define INT_ID_TMR1         NDS32_INT_H5
#define INT_ID_TMR2         NDS32_INT_H6
#define INT_ID_UART0        NDS32_INT_H7
#define INT_ID_USB1         NDS32_INT_H8
#define INT_ID_SDC          NDS32_INT_H9
#define INT_ID_ECDC         NDS32_INT_H10
#define INT_ID_LED          NDS32_INT_H11
#define INT_ID_SPI1         NDS32_INT_H12
#define INT_ID_UART1        NDS32_INT_H13
#define INT_ID_UART2        NDS32_INT_H14
#define INT_ID_UART3        NDS32_INT_H15
#define INT_VEC_ENTRY_SZ    16
#define INT_ADDR_SW         (INT_ID_SW*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_TMR0       (INT_ID_TMR0*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_GPIO       (INT_ID_GPIO*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_SPI0       (INT_ID_SPI0*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_SATA       (INT_ID_SATA*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_USB0       (INT_ID_USB0*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_TMR1       (INT_ID_TMR1*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_TMR2       (INT_ID_TMR2*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_UART0      (INT_ID_UART0*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_USB1       (INT_ID_USB1*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_SDC        (INT_ID_SDC*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_ECDC       (INT_ID_ECDC*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_LED        (INT_ID_LED*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_SPI1       (INT_ID_SPI1*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_UART1      (INT_ID_UART1*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_UART2      (INT_ID_UART2*INT_VEC_ENTRY_SZ+144)
#define INT_ADDR_UART3      (INT_ID_UART3*INT_VEC_ENTRY_SZ+144)

#ifdef __cplusplus
}
#endif

#endif


#ifndef __CH568USBSFR_H__
#define __CH568USBSFR_H__

#ifdef __cplusplus
extern "C" {
#endif


#define USB0_BASE_ADDR              (0x00408000)
#define USB1_BASE_ADDR              (0x00409000)


#define		R32_USB0_CONTROL	(*((PUINT32V)(USB0_BASE_ADDR + 0x000)))
#define		R8_USB0_CTRL		(*((PUINT8V)(USB0_BASE_ADDR + 0x000)))
#define		R8_UHOST_CTRL0		(*((PUINT8V)(USB0_BASE_ADDR + 0x001)))
#define		R8_USB0_INT_EN		(*((PUINT8V)(USB0_BASE_ADDR + 0x002)))
#define		R8_USB0_DEV_AD		(*((PUINT8V)(USB0_BASE_ADDR + 0x003)))
#define		R32_USB0_FRAME_NO   (*((PUINT32V)(USB0_BASE_ADDR + 0x004)))
#define 	R16_USB0_SOF_NO   	(*((PUINT16V)(USB0_BASE_ADDR + 0x004)))
#define     R8_USB0_SUSPEND		(*((PUINT8V)(USB0_BASE_ADDR + 0x006)))
#define		R32_USB0_STATUS		(*((PUINT32V)(USB0_BASE_ADDR + 0x008)))
#define		R8_USB0_SPD_TYPE	(*((PUINT8V)(USB0_BASE_ADDR + 0x008)))
#define		R8_USB0_MIS_ST		(*((PUINT8V)(USB0_BASE_ADDR + 0x009)))
#define		R8_USB0_INT_FG		(*((PUINT8V)(USB0_BASE_ADDR + 0x00a)))
#define		R8_USB0_INT_ST		(*((PUINT8V)(USB0_BASE_ADDR + 0x00b)))
#define		R16_USB0_RX_LEN		(*((PUINT16V)(USB0_BASE_ADDR + 0x00c)))
#define		R32_USB0_BUF_MODE	(*((PUINT32V)(USB0_BASE_ADDR + 0x010)))
#define		R8_UEP4_1_MOD0		(*((PUINT8V)(USB0_BASE_ADDR + 0x010)))
#define		R8_UEP2_3_MOD0		(*((PUINT8V)(USB0_BASE_ADDR + 0x011)))
#define		R8_UH_EP_MOD0		R8_UEP2_3_MOD0
#define		R16_UEP0_DMA0		(*((PUINT16V)(USB0_BASE_ADDR + 0x014)))
#define		R16_UEP1_DMA0		(*((PUINT16V)(USB0_BASE_ADDR + 0x018)))
#define		R16_UEP2_DMA0		(*((PUINT16V)(USB0_BASE_ADDR + 0x01c)))
#define		R16_UEP3_DMA0		(*((PUINT16V)(USB0_BASE_ADDR + 0x020)))
#define		R16_UH_RX_DMA0		R16_UEP2_DMA0
#define		R16_UH_TX_DMA0		R16_UEP3_DMA0

#define 	R16_UEP0_MAX_LEN0	(*((PUINT16V)(USB0_BASE_ADDR + 0x024)))
#define		R16_UEP1_MAX_LEN0	(*((PUINT16V)(USB0_BASE_ADDR + 0x028)))
#define		R16_UEP2_MAX_LEN0	(*((PUINT16V)(USB0_BASE_ADDR + 0x02C)))
#define		R16_UEP3_MAX_LEN0	(*((PUINT16V)(USB0_BASE_ADDR + 0x030)))
#define		R16_UEP4_MAX_LEN0	(*((PUINT16V)(USB0_BASE_ADDR + 0x034)))
#define		R16_UH_RX_MAX_LEN0	R16_UEP2_MAX_LEN0

#define		R32_USB0_EP0_CTRL	(*((PUINT32V)(USB0_BASE_ADDR + 0x038)))
#define		R16_UEP0_T_LEN0		(*((PUINT16V)(USB0_BASE_ADDR + 0x038)))
#define		R8_UEP0_TX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x03a)))
#define		R8_UEP0_RX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x03b)))
#define		R32_USB0_EP1_CTRL	(*((PUINT32V)(USB0_BASE_ADDR + 0x03c)))
#define		R16_UEP1_T_LEN0		(*((PUINT16V)(USB0_BASE_ADDR + 0x03c)))
#define		R8_UEP1_TX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x03e)))
#define		R8_UEP1_RX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x03f)))
#define		R8_UH_SETUP0		R8_UEP1_TX_CTRL0
#define		R32_USB0_EP2_CTRL	(*((PUINT32V)(USB0_BASE_ADDR + 0x040)))
#define		R16_UEP2_T_LEN0		(*((PUINT16V)(USB0_BASE_ADDR + 0x040)))
#define		R8_UEP2_TX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x042)))
#define		R8_UEP2_RX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x043)))
#define		R8_UH_EP_PID0		(*((PUINT8V)(USB0_BASE_ADDR + 0x040)))
#define		R8_UH_RX_CTRL0		R8_UEP2_RX_CTRL0
#define		R32_USB0_EP3_CTRL	(*((PUINT32V)(USB0_BASE_ADDR + 0x044)))
#define		R16_UEP3_T_LEN0		(*((PUINT16V)(USB0_BASE_ADDR + 0x044)))
#define		R8_UEP3_TX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x046)))
#define		R8_UEP3_RX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x047)))
#define		R16_UH_TX_LEN0		R16_UEP3_T_LEN0
#define		R8_UH_TX_CTRL0		R8_UEP3_TX_CTRL0
#define		R32_USB0_EP4_CTRL	(*((PUINT32V)(USB0_BASE_ADDR + 0x048)))
#define		R16_UEP4_T_LEN0		(*((PUINT16V)(USB0_BASE_ADDR + 0x048)))
#define		R8_UEP4_TX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x04a)))
#define		R8_UEP4_RX_CTRL0	(*((PUINT8V)(USB0_BASE_ADDR + 0x04b)))
#define     R16_UH_SPLIT_DATA0   R16_UEP4_T_LEN0


#define		R32_USB1_CONTROL	(*((PUINT32V)(USB1_BASE_ADDR + 0x000)))
#define		R8_USB1_CTRL		(*((PUINT8V)(USB1_BASE_ADDR + 0x000)))
#define		R8_UHOST_CTRL1		(*((PUINT8V)(USB1_BASE_ADDR + 0x001)))
#define		R8_USB1_INT_EN		(*((PUINT8V)(USB1_BASE_ADDR + 0x002)))
#define		R8_USB1_DEV_AD		(*((PUINT8V)(USB1_BASE_ADDR + 0x003)))
#define		R32_USB1_FRAME_NO   (*((PUINT32V)(USB1_BASE_ADDR + 0x004)))
#define 	R16_USB1_SOF_NO   	(*((PUINT16V)(USB1_BASE_ADDR + 0x004)))
#define     R8_USB1_SUSPEND		(*((PUINT8V)(USB1_BASE_ADDR + 0x006)))
#define		R32_USB1_STATUS		(*((PUINT32V)(USB1_BASE_ADDR + 0x008)))
#define		R8_USB1_SPD_TYPE	(*((PUINT8V)(USB1_BASE_ADDR + 0x008)))
#define		R8_USB1_MIS_ST		(*((PUINT8V)(USB1_BASE_ADDR + 0x009)))
#define		R8_USB1_INT_FG		(*((PUINT8V)(USB1_BASE_ADDR + 0x00a)))
#define		R8_USB1_INT_ST		(*((PUINT8V)(USB1_BASE_ADDR + 0x00b)))
#define		R16_USB1_RX_LEN		(*((PUINT16V)(USB1_BASE_ADDR + 0x00c)))
#define		R32_USB1_BUF_MODE	(*((PUINT32V)(USB1_BASE_ADDR + 0x010)))
#define		R8_UEP4_1_MOD1		(*((PUINT8V)(USB1_BASE_ADDR + 0x010)))
#define		R8_UEP2_3_MOD1		(*((PUINT8V)(USB1_BASE_ADDR + 0x011)))
#define		R8_UH_EP_MOD1		R8_UEP2_3_MOD1
#define		R16_UEP0_DMA1		(*((PUINT16V)(USB1_BASE_ADDR + 0x014)))
#define		R16_UEP1_DMA1		(*((PUINT16V)(USB1_BASE_ADDR + 0x018)))
#define		R16_UEP2_DMA1		(*((PUINT16V)(USB1_BASE_ADDR + 0x01c)))
#define		R16_UEP3_DMA1		(*((PUINT16V)(USB1_BASE_ADDR + 0x020)))
#define		R16_UH_RX_DMA1		R16_UEP2_DMA1
#define		R16_UH_TX_DMA1		R16_UEP3_DMA1

#define 	R16_UEP0_MAX_LEN1	(*((PUINT16V)(USB1_BASE_ADDR + 0x024)))
#define		R16_UEP1_MAX_LEN1	(*((PUINT16V)(USB1_BASE_ADDR + 0x028)))
#define		R16_UEP2_MAX_LEN1	(*((PUINT16V)(USB1_BASE_ADDR + 0x02C)))
#define		R16_UEP3_MAX_LEN1	(*((PUINT16V)(USB1_BASE_ADDR + 0x030)))
#define		R16_UEP4_MAX_LEN1	(*((PUINT16V)(USB1_BASE_ADDR + 0x034)))
#define		R16_UH_RX_MAX_LEN1	R16_UEP2_MAX_LEN1

#define		R32_USB1_EP0_CTRL	(*((PUINT32V)(USB1_BASE_ADDR + 0x038)))
#define		R16_UEP0_T_LEN1		(*((PUINT16V)(USB1_BASE_ADDR + 0x038)))
#define		R8_UEP0_TX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x03a)))
#define		R8_UEP0_RX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x03b)))
#define		R32_USB1_EP1_CTRL	(*((PUINT32V)(USB1_BASE_ADDR + 0x03c)))
#define		R16_UEP1_T_LEN1		(*((PUINT16V)(USB1_BASE_ADDR + 0x03c)))
#define		R8_UEP1_TX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x03e)))
#define		R8_UEP1_RX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x03f)))
#define		R8_UH_SETUP1		R8_UEP1_TX_CTRL1
#define		R32_USB1_EP2_CTRL	(*((PUINT32V)(USB1_BASE_ADDR + 0x040)))
#define		R16_UEP2_T_LEN1		(*((PUINT16V)(USB1_BASE_ADDR + 0x040)))
#define		R8_UEP2_TX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x042)))
#define		R8_UEP2_RX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x043)))
#define		R8_UH_EP_PID1		(*((PUINT8V)(USB1_BASE_ADDR + 0x040)))
#define		R8_UH_RX_CTRL1		R8_UEP2_RX_CTRL1
#define		R32_USB1_EP3_CTRL	(*((PUINT32V)(USB1_BASE_ADDR + 0x044)))
#define		R16_UEP3_T_LEN1		(*((PUINT16V)(USB1_BASE_ADDR + 0x044)))
#define		R8_UEP3_TX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x046)))
#define		R8_UEP3_RX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x047)))
#define		R16_UH_TX_LEN1		R16_UEP3_T_LEN1
#define		R8_UH_TX_CTRL1		R8_UEP3_TX_CTRL1
#define		R32_USB1_EP4_CTRL	(*((PUINT32V)(USB1_BASE_ADDR + 0x048)))
#define		R16_UEP4_T_LEN1		(*((PUINT16V)(USB1_BASE_ADDR + 0x048)))
#define		R8_UEP4_TX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x04a)))
#define		R8_UEP4_RX_CTRL1	(*((PUINT8V)(USB1_BASE_ADDR + 0x04b)))
#define     R16_UH_SPLIT_DATA1   R16_UEP4_T_LEN1


#define UST_FS 0x00
#define UST_HS 0x01
#define UST_LS 0x02


#define bUS_RESUME  0x02
#define bUS_SUSPEND 0x01


#define bUEP_AUTO_TOG     0x20
#define MASK_UEP_T_TOG    0x18
#define bUEP_T_RES_NO     0x04
#define MASK_UEP_T_RES    0x03

#define UEP_T_RES_ACK     0x00
#define UEP_T_RES_NAK     0x02
#define UEP_T_RES_STALL   0x03


#define MASK_UEP_R_TOG    0x18
#define bUEP_R_RES_NO     0x04
#define MASK_UEP_R_RES    0x03

#define UEP_R_RES_ACK     0x00
#define UEP_R_RES_NAK     0x02
#define UEP_R_RES_STALL   0x03
#define UEP_R_RES_NYET	  0x01


#define UEP_DATA0   (0x00<<3)
#define UEP_DATA1   (0x01<<3)
#define UEP_DATA2   (0x02<<3)
#define UEP_MDATA	(0x03<<3)


#define UIF_FIFO_OV   0x10
#define UIF_HST_SOF   0x08
#define UIF_SUSPEND   0x04
#define UIF_TRANSFER  0x02
#define UIF_DETECT    0x01
#define UIF_BUS_RST   0x01


#define bUIS_IS_NAK       0x80
#define bUIS_TOG_OK       0x40
#define MASK_UIS_TOKEN    0x30
#define MASK_UIS_ENDP     0x0F
#define MASK_UIS_H_RES    0x0F

#define UIS_TOKEN_OUT     0x00
#define UIS_TOKEN_SOF     0x10
#define UIS_TOKEN_IN      0x20
#define UIS_TOKEN_SETUP   0x30


#define bUMS_SOF_PRES     0x80
#define bUMS_SOF_ACT      0x40
#define bUMS_SIE_FREE     0x20
#define bUMS_R_FIFO_RDY   0x10
#define bUMS_BUS_RESET    0x08
#define bUMS_SUSPEND      0x04
#define bUMS_ATTACH    	  0x02
#define bUMS_SPLIT_CAN    0x01


#define bUIE_DEV_SOF      0x80
#define bUIE_DEV_NAK      0x40
#define bUIE_FIFO_OV      0x10
#define bUIE_HST_SOF      0x08
#define bUIE_SUSPEND      0x04
#define bUIE_TRANSFER     0x02
#define bUIE_DETECT       0x01
#define bUIE_BUS_RST      0x01


#define bUC_HOST_MODE     0x80
#define UC_SPEED_TYPE     0x60
#define bUC_DEV_PU_EN     0x10
#define bUC_INT_BUSY      0x08
#define bUC_RESET_SIE     0x04
#define bUC_CLR_ALL       0x02
#define bUC_DMA_EN        0x01


#define UCST_FS 0x00
#define UCST_HS 0x20
#define UCST_LS 0x40


#define bUH_SOF_EN        0x40


#define bUH_R_DATA_NO   0x40
#define bUH_R_AUTO_TOG	0x20
#define MASK_UH_R_TOG	0x18
#define bUH_R_RES_NO	0x04
#define MASK_UH_R_RES   0x03


#define bUH_T_DATA_NO   0x40
#define bUH_T_AUTO_TOG 	0x20
#define MASK_UH_T_TOG 	0x18
#define bUH_T_RES_NO	0x04
#define MASK_UH_T_RES   0x03


#define UH_DATA0	(0x00<<3)
#define UH_DATA1	(0x01<<3)
#define UH_DATA2	(0x02<<3)
#define UH_MDATA	(0x03<<3)


#define UH_ACK		0x00
#define UH_NAK		0x02
#define UH_STALL	0x03
#define UH_NYET		0x01


#define MASK_UH_TOKEN     0xF0
#define MASK_UH_ENDP      0x0F


#define bUH_TX_BUS_RESUME  0x04
#define bUH_TX_BUS_SUSPEND 0x02
#define bUH_TX_BUS_RESET   0x01


#define bUEP1_RX_EN       0x80
#define bUEP1_TX_EN       0x40
#define bUEP1_BUF_MOD     0x10


#define bUEP4_RX_EN       0x08
#define bUEP4_TX_EN       0x04


#define bUEP3_RX_EN       0x80
#define bUEP3_TX_EN       0x40
#define bUEP3_BUF_MOD     0x10
#define bUEP2_RX_EN       0x08
#define bUEP2_TX_EN       0x04
#define bUEP2_BUF_MOD     0x01


#define bUH_EP_TX_EN      0x40
#define bUH_EP_TBUF_MOD   0x10


#define bUH_EP_RX_EN      0x08
#define bUH_EP_RBUF_MOD   0x01


#ifdef __cplusplus
}
#endif

#endif


#ifndef __USB_TYPE__
#define __USB_TYPE__

#ifdef __cplusplus
extern "C" {
#endif


#define USB_DEV_SPEED_LS		0x01
#define USB_DEV_SPEED_FS		0x00
#define USB_DEV_SPEED_HS		0x02


#ifndef USB_PID_SETUP
#define USB_PID_NULL            0x00
#define USB_PID_PING    		0x04
#define USB_PID_SOF             0x05
#define USB_PID_SETUP           0x0D
#define USB_PID_IN              0x09
#define USB_PID_OUT             0x01
#define USB_PID_ACK             0x02
#define USB_PID_NAK             0x0A
#define USB_PID_STALL           0x0E
#define USB_PID_NYET	        0x06
#define USB_PID_DATA0           0x03
#define USB_PID_DATA1           0x0B
#define USB_PID_PRE             0x0C
#define USB_PID_ERR     		0x0C
#define USB_PID_SPLIT           0x08
#define USB_PID_DATA0   		0x03
#define USB_PID_DATA1   		0x0B
#define USB_PID_DATA2   		0x07
#define USB_PID_MDATA   		0x0F
#endif


#ifndef USB_GET_DESCRIPTOR
#define USB_GET_STATUS          0x00
#define USB_CLEAR_FEATURE       0x01
#define USB_SET_FEATURE         0x03
#define USB_SET_ADDRESS         0x05
#define USB_GET_DESCRIPTOR      0x06
#define USB_SET_DESCRIPTOR      0x07
#define USB_GET_CONFIGURATION   0x08
#define USB_SET_CONFIGURATION   0x09
#define USB_GET_INTERFACE       0x0A
#define USB_SET_INTERFACE       0x0B
#define USB_SYNCH_FRAME         0x0C
#endif


#ifndef HUB_GET_DESCRIPTOR
#define HUB_GET_STATUS          0x00
#define HUB_CLEAR_FEATURE       0x01
#define HUB_GET_STATE           0x02
#define HUB_SET_FEATURE         0x03
#define HUB_GET_DESCRIPTOR      0x06
#define HUB_SET_DESCRIPTOR      0x07
#endif


#ifndef HID_GET_REPORT
#define HID_GET_REPORT          0x01
#define HID_GET_IDLE            0x02
#define HID_GET_PROTOCOL        0x03
#define HID_SET_REPORT          0x09
#define HID_SET_IDLE            0x0A
#define HID_SET_PROTOCOL        0x0B
#endif


#ifndef USB_REQ_TYP_MASK
#define USB_REQ_TYP_IN          0x80
#define USB_REQ_TYP_OUT         0x00
#define USB_REQ_TYP_READ        0x80
#define USB_REQ_TYP_WRITE       0x00
#define USB_REQ_TYP_MASK        0x60
#define USB_REQ_TYP_STANDARD    0x00
#define USB_REQ_TYP_CLASS       0x20
#define USB_REQ_TYP_VENDOR      0x40
#define USB_REQ_TYP_RESERVED    0x60
#define USB_REQ_RECIP_MASK      0x1F
#define USB_REQ_RECIP_DEVICE    0x00
#define USB_REQ_RECIP_INTERF    0x01
#define USB_REQ_RECIP_ENDP      0x02
#define USB_REQ_RECIP_OTHER     0x03
#endif


#ifndef HUB_GET_HUB_DESCRIPTOR
#define HUB_CLEAR_HUB_FEATURE   0x20
#define HUB_CLEAR_PORT_FEATURE  0x23
#define HUB_GET_BUS_STATE       0xA3
#define HUB_GET_HUB_DESCRIPTOR  0xA0
#define HUB_GET_HUB_STATUS      0xA0
#define HUB_GET_PORT_STATUS     0xA3
#define HUB_SET_HUB_DESCRIPTOR  0x20
#define HUB_SET_HUB_FEATURE     0x20
#define HUB_SET_PORT_FEATURE    0x23
#endif


#ifndef HUB_PORT_RESET
#define HUB_C_HUB_LOCAL_POWER   0
#define HUB_C_HUB_OVER_CURRENT  1
#define HUB_PORT_CONNECTION     0
#define HUB_PORT_ENABLE         1
#define HUB_PORT_SUSPEND        2
#define HUB_PORT_OVER_CURRENT   3
#define HUB_PORT_RESET          4
#define HUB_PORT_POWER          8
#define HUB_PORT_LOW_SPEED      9
#define HUB_C_PORT_CONNECTION   16
#define HUB_C_PORT_ENABLE       17
#define HUB_C_PORT_SUSPEND      18
#define HUB_C_PORT_OVER_CURRENT 19
#define HUB_C_PORT_RESET        20
#endif


#ifndef USB_DESCR_TYP_DEVICE
#define USB_DESCR_TYP_DEVICE    0x01
#define USB_DESCR_TYP_CONFIG    0x02
#define USB_DESCR_TYP_STRING    0x03
#define USB_DESCR_TYP_INTERF    0x04
#define USB_DESCR_TYP_ENDP      0x05
#define USB_DESCR_TYP_QUALIF    0x06
#define USB_DESCR_TYP_SPEED     0x07
#define USB_DESCR_TYP_OTG       0x09
#define USB_DESCR_TYP_HID       0x21
#define USB_DESCR_TYP_REPORT    0x22
#define USB_DESCR_TYP_PHYSIC    0x23
#define USB_DESCR_TYP_CS_INTF   0x24
#define USB_DESCR_TYP_CS_ENDP   0x25
#define USB_DESCR_TYP_HUB       0x29
#endif


#ifndef USB_DEV_CLASS_HUB
#define USB_DEV_CLASS_RESERVED  0x00
#define USB_DEV_CLASS_AUDIO     0x01
#define USB_DEV_CLASS_COMMUNIC  0x02
#define USB_DEV_CLASS_HID       0x03
#define USB_DEV_CLASS_MONITOR   0x04
#define USB_DEV_CLASS_PHYSIC_IF 0x05
#define USB_DEV_CLASS_POWER     0x06
#define USB_DEV_CLASS_PRINTER   0x07
#define USB_DEV_CLASS_STORAGE   0x08
#define USB_DEV_CLASS_HUB       0x09
#define USB_DEV_CLASS_VEN_SPEC  0xFF
#endif


#ifndef USB_ENDP_TYPE_MASK
#define USB_ENDP_DIR_MASK       0x80
#define USB_ENDP_ADDR_MASK      0x0F
#define USB_ENDP_TYPE_MASK      0x03
#define USB_ENDP_TYPE_CTRL      0x00
#define USB_ENDP_TYPE_ISOCH     0x01
#define USB_ENDP_TYPE_BULK      0x02
#define USB_ENDP_TYPE_INTER     0x03
#endif

#ifndef USB_DEVICE_ADDR
#define	USB_DEVICE_ADDR			0x02
#endif
#ifndef DEFAULT_ENDP0_SIZE
#define DEFAULT_ENDP0_SIZE      64
#endif
#ifndef MAX_PACKET_SIZE
#define MAX_PACKET_SIZE         512
#endif
#ifndef USB_BO_CBW_SIZE
#define USB_BO_CBW_SIZE			0x1F
#define USB_BO_CSW_SIZE			0x0D
#endif
#ifndef USB_BO_CBW_SIG0
#define USB_BO_CBW_SIG0         0x55
#define USB_BO_CBW_SIG1         0x53
#define USB_BO_CBW_SIG2         0x42
#define USB_BO_CBW_SIG3         0x43
#define USB_BO_CSW_SIG0         0x55
#define USB_BO_CSW_SIG1         0x53
#define USB_BO_CSW_SIG2         0x42
#define USB_BO_CSW_SIG3         0x53
#endif

#ifndef USB_SETUP_REQ
typedef struct _USB_SETUP_REQ {
    UINT8 bRequestType;
    UINT8 bRequest;
    UINT8 wValueL;
    UINT8 wValueH;
    UINT8 wIndexL;
    UINT8 wIndexH;
    UINT8 wLengthL;
    UINT8 wLengthH;
} USB_SETUP_REQ, *PUSB_SETUP_REQ;
#endif

#ifndef USB_DEV_DESCR
typedef struct _USB_DEVICE_DESCR {
    UINT8 bLength;
    UINT8 bDescriptorType;
    UINT8 bcdUSBL;
    UINT8 bcdUSBH;
    UINT8 bDeviceClass;
    UINT8 bDeviceSubClass;
    UINT8 bDeviceProtocol;
    UINT8 bMaxPacketSize0;
    UINT8 idVendorL;
    UINT8 idVendorH;
    UINT8 idProductL;
    UINT8 idProductH;
    UINT8 bcdDeviceL;
    UINT8 bcdDeviceH;
    UINT8 iManufacturer;
    UINT8 iProduct;
    UINT8 iSerialNumber;
    UINT8 bNumConfigurations;
} USB_DEV_DESCR, *PUSB_DEV_DESCR;
#endif

#ifndef USB_CFG_DESCR
typedef struct _USB_CONFIG_DESCR {
    UINT8 bLength;
    UINT8 bDescriptorType;
    UINT8 wTotalLengthL;
    UINT8 wTotalLengthH;
    UINT8 bNumInterfaces;
    UINT8 bConfigurationValue;
    UINT8 iConfiguration;
    UINT8 bmAttributes;
    UINT8 MaxPower;
} USB_CFG_DESCR, *PUSB_CFG_DESCR;
#endif

#ifndef USB_ITF_DESCR
typedef struct _USB_INTERF_DESCR {
    UINT8 bLength;
    UINT8 bDescriptorType;
    UINT8 bInterfaceNumber;
    UINT8 bAlternateSetting;
    UINT8 bNumEndpoints;
    UINT8 bInterfaceClass;
    UINT8 bInterfaceSubClass;
    UINT8 bInterfaceProtocol;
    UINT8 iInterface;
} USB_ITF_DESCR, *PUSB_ITF_DESCR;
#endif

#ifndef USB_ENDP_DESCR
typedef struct _USB_ENDPOINT_DESCR {
    UINT8 bLength;
    UINT8 bDescriptorType;
    UINT8 bEndpointAddress;
    UINT8 bmAttributes;
    UINT8 wMaxPacketSizeL;
    UINT8 wMaxPacketSizeH;
    UINT8 bInterval;
} USB_ENDP_DESCR, *PUSB_ENDP_DESCR;
#endif

#ifndef USB_CFG_DESCR_LONG
typedef struct _USB_CONFIG_DESCR_LONG {
    USB_CFG_DESCR   cfg_descr;
    USB_ITF_DESCR   itf_descr;
    USB_ENDP_DESCR  endp_descr[1];
} USB_CFG_DESCR_LONG, *PUSB_CFG_DESCR_LONG;
#endif

#ifndef USB_HUB_DESCR
typedef struct _USB_HUB_DESCR {
    UINT8 bDescLength;
    UINT8 bDescriptorType;
    UINT8 bNbrPorts;
    UINT8 wHubCharacteristicsL;
    UINT8 wHubCharacteristicsH;
    UINT8 bPwrOn2PwrGood;
    UINT8 bHubContrCurrent;
    UINT8 DeviceRemovable;
    UINT8 PortPwrCtrlMask;
} USB_HUB_DESCR, *PUSB_HUB_DESCR;
#endif

#ifndef USB_HID_DESCR
typedef struct _USB_HID_DESCR {
    UINT8 bLength;
    UINT8 bDescriptorType;
    UINT8 bcdHIDL;
    UINT8 bcdHIDH;
    UINT8 bCountryCode;
    UINT8 bNumDescriptors;
    UINT8 bDescriptorTypeX;
    UINT8 wDescriptorLengthL;
    UINT8 wDescriptorLengthH;
} USB_HID_DESCR, *PUSB_HID_DESCR;
#endif

#ifndef USB_DEV_QUAL_DESCR
typedef struct _USB_DEVICE_QUALIFIER_DESCRIPTOR
{
	UINT8  bLength;
	UINT8  bDescriptorType;
	UINT8  bcdUSBL;
	UINT8  bcdUSBH;
	UINT8  bDeviceClass;
	UINT8  bDeviceSubClass;
	UINT8  bDeviceProtocol;
	UINT8  bMaxPacketSize0;
	UINT8  bNumConfigurations;
	UINT8  bReserved;
}USB_DEV_QUAL_DESCR, *PUSB_DEV_QUAL_DESCR;
#endif

#ifndef USB_CFG_PWR_DESCR
typedef struct _USB_CONFIGURATION_POWER_DESCRIPTOR
{
	UINT8  bLength;
	UINT8  bDescriptorType;
	UINT8  SelfPowerConsumedD0[3];
	UINT8  bPowerSummaryId;
	UINT8  bBusPowerSavingD1;
	UINT8  bSelfPowerSavingD1;
	UINT8  bBusPowerSavingD2;
	UINT8  bSelfPowerSavingD2;
	UINT8  bBusPowerSavingD3;
	UINT8  bSelfPowerSavingD3;
	UINT8  TransitionTimeFromD1L;
	UINT8  TransitionTimeFromD1H;
	UINT8  TransitionTimeFromD2L;
	UINT8  TransitionTimeFromD2H;
	UINT8  TransitionTimeFromD3L;
	UINT8  TransitionTimeFromD3H;
}USB_CFG_PWR_DESCR, *PUSB_CFG_PWR_DESCR;
#endif

#ifndef USB_ITF_PWR_DESCR
typedef struct _USB_INTERFACE_POWER_DESCRIPTOR
{
	UINT8  bLength;
	UINT8  bDescriptorType;
	UINT8  bmCapabilitiesFlags;
	UINT8  bBusPowerSavingD1;
	UINT8  bSelfPowerSavingD1;
	UINT8  bBusPowerSavingD2;
	UINT8  bSelfPowerSavingD2;
	UINT8  bBusPowerSavingD3;
	UINT8  bSelfPowerSavingD3;
	UINT8  TransitionTimeFromD1L;
	UINT8  TransitionTimeFromD1H;
	UINT8  TransitionTimeFromD2L;
	UINT8  TransitionTimeFromD2H;
	UINT8  TransitionTimeFromD3L;
	UINT8  TransitionTimeFromD3H;
}USB_ITF_PWR_DESCR, *PUSB_ITF_PWR_DESCR;
#endif

#define USB_BO_CBW_SIG              0x43425355
#define USB_BO_CSW_SIG              0x53425355

typedef union _BULK_ONLY_CMD
{
    struct
    {
        UINT32 mCBW_Sig;
        UINT32 mCBW_Tag;
        UINT32 mCBW_DataLen;
        UINT8  mCBW_Flag;
        UINT8  mCBW_LUN;
        UINT8  mCBW_CB_Len;
        UINT8  mCBW_CB_Buf[16];
    } mCBW;
    struct
    {
        UINT32 mCSW_Sig;
        UINT32 mCSW_Tag;
        UINT32 mCSW_Residue;
        UINT8  mCSW_Status;
    } mCSW;
} BULK_ONLY_CMD, *PBULK_ONLY_CMD;


#ifdef __cplusplus
}
#endif

#endif


#ifndef __CH568SATASFR_H__
#define __CH568SATASFR_H__

#ifdef __cplusplus
extern "C" {
#endif


#define SATA_BASE_ADDR          (0x0040B000)

#define R32_SATA_CONTROL		(*((PUINT32V)(SATA_BASE_ADDR + 0x000)))
#define R8_SATA_CTRL			(*((PUINT8V)(SATA_BASE_ADDR + 0x000)))
#define R8_SATA_PM_CTRL			(*((PUINT8V)(SATA_BASE_ADDR + 0x001)))
#define R8_SATA_MOD				(*((PUINT8V)(SATA_BASE_ADDR + 0x002)))
#define R16_SATA_INT_EN			(*((PUINT16V)(SATA_BASE_ADDR + 0x004)))
#define R8_SATA_INT_EN_L		(*((PUINT8V)(SATA_BASE_ADDR + 0x004)))
#define R8_SATA_INT_EN_H		(*((PUINT8V)(SATA_BASE_ADDR + 0x005)))
#define R16_SATA_RX_LEN			(*((PUINT16V)(SATA_BASE_ADDR + 0x008)))
#define R32_SATA_STATUS			(*((PUINT32V)(SATA_BASE_ADDR + 0x00C)))
#define R16_SATA_INT_FG			(*((PUINT16V)(SATA_BASE_ADDR + 0x00C)))
#define R8_SATA_INT_FG_L		(*((PUINT8V)(SATA_BASE_ADDR + 0x00C)))
#define R8_SATA_INT_FG_H		(*((PUINT8V)(SATA_BASE_ADDR + 0x00D)))
#define R8_SATA_INT_ST	 		(*((PUINT8V)(SATA_BASE_ADDR + 0x00E)))
#define R32_SATA_RTX_CONTROL 	(*((PUINT32V)(SATA_BASE_ADDR + 0x010)))
#define R16_SATA_TX_LEN			(*((PUINT16V)(SATA_BASE_ADDR + 0x010)))
#define R8_SATA_RTX_CTRL	 	(*((PUINT8V)(SATA_BASE_ADDR + 0x012)))
#define R32_SATA_DATA0			(*((PUINT32V)(SATA_BASE_ADDR + 0x014)))
#define R32_SATA_DATA1			(*((PUINT32V)(SATA_BASE_ADDR + 0x018)))
#define R32_SATA_DMA			(*((PUINT32V)(SATA_BASE_ADDR + 0x01C)))
#define R16_SATA_DMA0			(*((PUINT16V)(SATA_BASE_ADDR + 0x01C)))
#define	R16_SATA_DMA1			(*((PUINT16V)(SATA_BASE_ADDR + 0x01E)))


#define bSC_DMA_EN			0x80
#define bSC_CONT_EN			0x40
#define bSC_HOST_MODE		0x20
#define	bSC_FORCE_1P5G		0x10
#define bSC_INT_BUSY		0x08
#define bSC_RESET_PHY		0x04
#define bSC_RESET_LINK		0x02
#define bSC_CLR_ALL			0x01


#define bSPC_OFFLINE		0x80
#define bSPC_LISTEN			0x40
#define bSPC_SLUMBER_S		0x20
#define bSPC_SLUMBER		0x10
#define bSPC_PARTIAL		0x08
#define bSPC_SEND_PMREQ_P	0x04
#define bSPC_SEND_PMREQ_S	0x02
#define bSPC_DENY			0x01


#define bSM_RX_EN			0x04
#define bSM_TX_EN			0x02
#define bSM_BUF_MOD			0x01


#define bSIE_TRAN_INT		0x0080
#define bSIE_HOLD			0x0040
#define	bSIE_DMAT			0x0020
#define bSIE_FIFO_OV		0x0010
#define bSIE_COLLIDE		0x0008
#define bSIE_RECV_OK		0x0004
#define bSIE_TRAN_OK   	 	0x0002
#define bSIE_PHYRDY			0x0001

#define	bSIE_COMWAKE		0x1000
#define bSIE_COMINIT		0x0800
#define bSIE_PHYERR     	0x0400
#define bSIE_PM_REQ			0x0200
#define bSIE_PM_RES			0x0100


#define bSIF_TRAN_INT		0x0080
#define bSIF_HOLD			0x0040
#define	bSIF_DMAT			0x0020
#define bSIF_FIFO_OV		0x0010
#define bSIF_COLLIDE		0x0008
#define bSIF_RECV_OK		0x0004
#define bSIF_TRAN_OK   	 	0x0002
#define bSIF_PHYRDY			0x0001

#define bSIF_COMWAKE		0x2000
#define	bSIF_COMINIT		0x1000
#define bSIF_PHYERR     	0x0800
#define bSIF_PM_PARTIAL		0x0400
#define bSIF_PM_SLUMBER		0x0200
#define bSIF_PM_NAK			0x0100


#define bSMS_SPD_TYPE	    0x40
#define bSMS_R_FIFO_RDY     0x20
#define bSIS_LINK_FREE	    0x10
#define bSIS_HOLD		    0x08
#define bSIS_RECV_CRC_OK    0x04
#define bSIS_TRAN_CRC_OK    0x02
#define bSIS_PHYRDY		    0x01


#define bSRC_R_AUTO_TOG		0x80
#define bSRC_T_AUTO_TOG		0x40
#define bSRC_R_TOG			0x20
#define	bSRC_T_TOG			0x10
#define bSRC_R_READY		0x04
#define bSRC_T_READY		0x02
#define bSRC_SYNC_ESCAPE	0x01


#ifdef __cplusplus
}
#endif

#endif


#ifndef __SATA_TYPE__
#define __SATA_TYPE__

#ifdef __cplusplus
extern "C" {
#endif


#ifndef SATA_FIS_TYPE
#define SATA_FIS_REGHOST	  	0x27
#define SATA_FIS_REGDEVICE	  	0x34
#define SATA_FIS_PIOSETUP	  	0x5f
#define SATA_FIS_DMAACT		  	0x39
#define SATA_FIS_DMASETUP	  	0x41
#define SATA_FIS_TRANDATA	  	0x46
#define SATA_FIS_BIST		  	0x58
#define SATA_FIS_SETBIT		  	0xA1
#endif


#ifndef SATA_CMD_TYPE

#define SATA_CMD_IDENTIFY  		0xEC
#define SATA_CMD_IEFYPDEV  		0xA1
#define SATA_CMD_READBUFF       0xE4
#define SATA_CMD_READLOGE       0x2F
#define SATA_CMD_READMUL       	0xC4
#define SATA_CMD_READMULE       0x29
#define SATA_CMD_READSECS       0x20
#define SATA_CMD_READSECSE      0x24


#define SATA_CMD_SCYUNLOCK	    0xF2
#define SATA_CMD_WRITEBUFF	    0xE8
#define SATA_CMD_WRITELOGE      0x3F
#define SATA_CMD_WRITEMUL	    0xC5
#define SATA_CMD_WRITEMULE	    0x39
#define SATA_CMD_WRITESECS	    0x30
#define SATA_CMD_WRITESECSE	    0x34


#define SATA_CMD_READDMA	    0xC8
#define SATA_CMD_READDMAE       0x25


#define SATA_CMD_WRITEDMA       0xCA
#define SATA_CMD_WRITEDMAE      0x35


#define SATA_CMD_IDLE		    0xE3
#define SATA_CMD_SETFEATURE     0xEF
#define SATA_CMD_SETMULMODE     0xC6
#define SATA_CMD_SECYLOCK       0xF5
#define SATA_CMD_IDLEIMMDE      0xE1
#define SATA_CMD_DEVCONFG       0xB1
#define SATA_CMD_SMART          0xB0
#define SATA_CMD_STANDBY        0xE2
#define SATA_CMD_STANDBYIMMDE   0xE0
#define SATA_CMD_READVRYSEC     0x40
#define SATA_CMD_FLUSHCACHE     0xE7
#endif

#ifndef SATA_PACKET_STRUCT
typedef union _CTRLPARAM {
	struct
	{
	    UINT8 bFIStype;
	    UINT8 bPMport;
	    UINT8 bCommand;
	    UINT8 bFeathres;
	}SHADOW_HOST_CTRL;
	struct
	{
		UINT8 bFIStype;
		UINT8 bPMport;
	    UINT8 bStatus;
	    UINT8 bError;
	}SHADOW_Device_CTRL;
	struct
	{
		UINT8 bFIStype;
		UINT8 bPMport;
	    UINT8 bStatus;
	    UINT8 bError;
	}PIO_SETUP_CTRL;
	struct
	{
	    UINT8 bFIStype;
	    UINT8 bPMport;
	    UINT8 bReserved[2];
	}DMA_ACTIVE_CTRL;
	struct
	{
		UINT8 bFIStype;
		UINT8 bPMport;
	    UINT8 bReserved[2];
	}DMA_SETUP_CTRL;
	struct
	{
		UINT8 bFIStype;
		UINT8 bPMport;
	    UINT8 bReserved[2];
	}DATA_CTRL;
	struct
	{
		UINT8 bFIStype;
		UINT8 bPMport;
	    UINT8 bPattern;
	    UINT8 bReserved;
	}BIST_AVT_CTRL;
	struct
	{
		UINT8 bFIStype;
		UINT8 bPMport;
	    UINT8 bStatus;
	    UINT8 bError;
	}SET_DEV_CTRL;
}CTRLPARAM;

typedef union _DATAPARAM {
	struct
	{
	    UINT8 bLBALow;
		UINT8 bLBAMid;
		UINT8 bLBAHigh;
		UINT8 bDevice;
		UINT8 bLBALowE;
		UINT8 bLBAMidE;
		UINT8 bLBAHighE;
		UINT8 bFeathresE;
		UINT16 bSecCount;
		UINT8 bReserved_0;
		UINT8 bControl;
		UINT8 bReserved[4];
	}SHADOW_HOST_DATA;

	struct
	{
		UINT8 bLBALow;
	    UINT8 bLBAMid;
	    UINT8 bLBAHigh;
	    UINT8 bDevice;
	    UINT8 bLBALowE;
	    UINT8 bLBAMidE;
	    UINT8 bLBAHighE;
	    UINT8 bReserved_0;
	    UINT16 bSecCount;
	    UINT8 bReserved[6];
	}SHADOW_Device_DATA;

	struct
	{
		UINT8 bLBALow;
	    UINT8 bLBAMid;
	    UINT8 bLBAHigh;
	    UINT8 bDevice;
	    UINT8 bLBALowE;
	    UINT8 bLBAMidE;
	    UINT8 bLBAHighE;
	    UINT8 bReserved_0;
	    UINT16 bSecCount;
	    UINT8 bReserved_1;
	    UINT8 bEStatus;
	    UINT16 bTranCount;
	    UINT8 bReserved[2];
	}PIO_SETUP_DATA;

	struct
	{
		UINT32 bDMABuff_L;
	    UINT32 bDMABuff_H;
	    UINT32 bReserved2;
	    UINT32 bDMABuffOFFET;
	    UINT32 bDMATRANCOUNT;
	    UINT32 bReserved3;
	}DMA_SETUP_DATA;

	struct
	{
		UINT32 bData[2];
	}BIST_AVT_DATA;

	struct
	{
		UINT32 bReserved;
	}SET_DEV_DATA;
}DATAPARAM;
#endif

#ifndef SATA_REG_GROUP
typedef struct _TRANS_REG_GROUP {
	struct{
	    UINT8 bCommand;
	    UINT8 bDevice;
	    UINT8 bFeature;
	    UINT8 E_bFeature;
	    UINT8 bLBALow;
	    UINT8 bLBAMid;
	    UINT8 bLBAHigh;
	    UINT8 E_bLBALow;
	    UINT8 E_bLBAMid;
	    UINT8 E_bLBAHigh;
	    UINT8 bSecCount;
	    UINT8 E_bSecCount;
	    UINT8 bError;
	}CmdBlock;

    struct{
	    UINT8 bControl;
	    UINT8 bStatus;
	    UINT8 bAlterStatus;
	}CtrBlock;

	struct{
		UINT32 bDMABuff_L;
		UINT32 bDMABuff_H;
	    UINT32 bDMABuffOFFET;
	    UINT32 bDMATRANCOUNT;
	}DMABlock;

	UINT8 bFlagReg;

} TRANS_REG_GROUP, *PTRANS_REG_GROUP;


#define bHOB	 0x80
#define bSRST	 0x04
#define bNIEN	 0x02


#define bDEV	 0x20
#define bADDR	 0x0f


#define bBSY	 0x80
#define bDRDY	 0x40
#define bDF		 0x20
#define bDRQ	 0x08
#define bERR	 0x01


#define bABRT	 0x04


#define bFlag_A	 0x80
#define bFlag_C	 0x08
#define bFlag_I  0x04
#define bFlag_D  0x02
#define bFlag_N	 0x01

#endif

#ifdef __cplusplus
}
#endif

#endif


#ifndef __CH568SDC4SFR_H__
#define __CH568SDC4SFR_H__

#ifdef __cplusplus
extern "C" {
#endif


#define SD0_BASE_ADDR               (0x0040A000)
#define SD1_BASE_ADDR               (0x0040A040)
#define SD2_BASE_ADDR               (0x0040A080)
#define SD3_BASE_ADDR               (0x0040A0c0)


#define     R16_SD_CLK_CFG    	(*((PUINT16V)(SD0_BASE_ADDR+0x03c)))


#define     R32_SD0_ARGUMENT    (*((PUINT32V)(SD0_BASE_ADDR+0x000)))
#define     R16_SD0_CMD_SET     (*((PUINT16V)(SD0_BASE_ADDR+0x004)))
#define     R32_SD0_RESPONSE0   (*((PUINT32V)(SD0_BASE_ADDR+0x008)))
#define     R32_SD0_RESPONSE1   (*((PUINT32V)(SD0_BASE_ADDR+0x00c)))
#define     R32_SD0_RESPONSE2   (*((PUINT32V)(SD0_BASE_ADDR+0x010)))
#define     R32_SD0_RESPONSE3   (*((PUINT32V)(SD0_BASE_ADDR+0x014)))
#define     R32_SD0_WRITE_CONT	(*((PUINT32V)(SD0_BASE_ADDR+0x014)))
#define     R8_SD0_CTRL         (*((PUINT8V )(SD0_BASE_ADDR+0x018)))
#define     R8_SD0_TOCNT        (*((PUINT8V )(SD0_BASE_ADDR+0x01c)))
#define     R32_SD0_STATUS      (*((PUINT32V)(SD0_BASE_ADDR+0x020)))
#define     R16_SD0_INT_FG      (*((PUINT16V)(SD0_BASE_ADDR+0x024)))
#define     R16_SD0_INT_EN      (*((PUINT16V)(SD0_BASE_ADDR+0x028)))
#define     R16_SD0_DMA         (*((PUINT16V)(SD0_BASE_ADDR+0x02c)))
#define     R32_SD0_BLOCK_CFG   (*((PUINT32V)(SD0_BASE_ADDR+0x030)))
#define     R8_SD0_TRAN_MODE    (*((PUINT8V )(SD0_BASE_ADDR+0x034)))


#define     R32_SD1_ARGUMENT    (*((PUINT32V)(SD1_BASE_ADDR+0x000)))
#define     R16_SD1_CMD_SET     (*((PUINT16V)(SD1_BASE_ADDR+0x004)))
#define     R32_SD1_RESPONSE0   (*((PUINT32V)(SD1_BASE_ADDR+0x008)))
#define     R32_SD1_RESPONSE1   (*((PUINT32V)(SD1_BASE_ADDR+0x00c)))
#define     R32_SD1_RESPONSE2   (*((PUINT32V)(SD1_BASE_ADDR+0x010)))
#define     R32_SD1_RESPONSE3   (*((PUINT32V)(SD1_BASE_ADDR+0x014)))
#define     R32_SD1_WRITE_CONT	(*((PUINT32V)(SD0_BASE_ADDR+0x014)))
#define     R8_SD1_CTRL         (*((PUINT8V )(SD1_BASE_ADDR+0x018)))
#define     R8_SD1_TOCNT        (*((PUINT8V )(SD1_BASE_ADDR+0x01c)))
#define     R32_SD1_STATUS      (*((PUINT32V)(SD1_BASE_ADDR+0x020)))
#define     R16_SD1_INT_FG      (*((PUINT16V)(SD1_BASE_ADDR+0x024)))
#define     R16_SD1_INT_EN      (*((PUINT16V)(SD1_BASE_ADDR+0x028)))
#define     R16_SD1_DMA         (*((PUINT16V)(SD1_BASE_ADDR+0x02c)))
#define     R32_SD1_BLOCK_CFG   (*((PUINT32V)(SD1_BASE_ADDR+0x030)))
#define     R8_SD1_TRAN_MODE    (*((PUINT8V )(SD1_BASE_ADDR+0x034)))


#define     R32_SD2_ARGUMENT    (*((PUINT32V)(SD2_BASE_ADDR+0x000)))
#define     R16_SD2_CMD_SET     (*((PUINT16V)(SD2_BASE_ADDR+0x004)))
#define     R32_SD2_RESPONSE0   (*((PUINT32V)(SD2_BASE_ADDR+0x008)))
#define     R32_SD2_RESPONSE1   (*((PUINT32V)(SD2_BASE_ADDR+0x00c)))
#define     R32_SD2_RESPONSE2   (*((PUINT32V)(SD2_BASE_ADDR+0x010)))
#define     R32_SD2_RESPONSE3   (*((PUINT32V)(SD2_BASE_ADDR+0x014)))
#define     R32_SD2_WRITE_CONT	(*((PUINT32V)(SD0_BASE_ADDR+0x014)))
#define     R8_SD2_CTRL         (*((PUINT8V )(SD2_BASE_ADDR+0x018)))
#define     R8_SD2_TOCNT        (*((PUINT8V )(SD2_BASE_ADDR+0x01c)))
#define     R32_SD2_STATUS      (*((PUINT32V)(SD2_BASE_ADDR+0x020)))
#define     R16_SD2_INT_FG      (*((PUINT16V)(SD2_BASE_ADDR+0x024)))
#define     R16_SD2_INT_EN      (*((PUINT16V)(SD2_BASE_ADDR+0x028)))
#define     R16_SD2_DMA         (*((PUINT16V)(SD2_BASE_ADDR+0x02C)))
#define     R32_SD2_BLOCK_CFG   (*((PUINT32V)(SD2_BASE_ADDR+0x030)))
#define     R8_SD2_TRAN_MODE    (*((PUINT8V )(SD2_BASE_ADDR+0x034)))


#define     R32_SD3_ARGUMENT    (*((PUINT32V)(SD3_BASE_ADDR+0x000)))
#define     R16_SD3_CMD_SET     (*((PUINT16V)(SD3_BASE_ADDR+0x004)))
#define     R32_SD3_RESPONSE0   (*((PUINT32V)(SD3_BASE_ADDR+0x008)))
#define     R32_SD3_RESPONSE1   (*((PUINT32V)(SD3_BASE_ADDR+0x00c)))
#define     R32_SD3_RESPONSE2   (*((PUINT32V)(SD3_BASE_ADDR+0x010)))
#define     R32_SD3_RESPONSE3   (*((PUINT32V)(SD3_BASE_ADDR+0x014)))
#define     R32_SD3_WRITE_CONT	(*((PUINT32V)(SD0_BASE_ADDR+0x014)))
#define     R8_SD3_CTRL         (*((PUINT8V )(SD3_BASE_ADDR+0x018)))
#define     R8_SD3_TOCNT        (*((PUINT8V )(SD3_BASE_ADDR+0x01c)))
#define     R32_SD3_STATUS      (*((PUINT32V)(SD3_BASE_ADDR+0x020)))
#define     R16_SD3_INT_FG      (*((PUINT16V)(SD3_BASE_ADDR+0x024)))
#define     R16_SD3_INT_EN      (*((PUINT16V)(SD3_BASE_ADDR+0x028)))
#define     R16_SD3_DMA         (*((PUINT16V)(SD3_BASE_ADDR+0x02C)))
#define     R32_SD3_BLOCK_CFG   (*((PUINT32V)(SD3_BASE_ADDR+0x030)))
#define     R8_SD3_TRAN_MODE    (*((PUINT8V )(SD3_BASE_ADDR+0x034)))


#define bSDCLK_Mode 	    0x200
#define bSDCLK_OE		    0x100
#define MASK_SD_CLK_PRE		0x01F


#define bCHK_RESP_IDX	    0x800
#define bCHK_RESP_CRC	    0x400
#define	MASK_RESP_TYPE		0x300
	#define RESP_TYPE_NO	    0x000
	#define RESP_TYPE_136	    0x100
	#define RESP_TYPE_48	    0x200
	#define RESP_TYPE_R1b	    0x300
#define	MASK_CMD_IDX			0x03F


#define bSC_NEG_SAMPLE      0x0020
#define bSC_RST_DAT_LGC     0x0010
#define bSC_DMA_ENABLE      0x0008
#define bSC_ALL_CLR         0x0004
#define DAT_LINE_WIDTH	    0x0003
	#define bSC_OP_DAT8         0x0002
	#define bSC_OP_DAT4         0x0001
	#define bSC_OP_DAT0         0x0000


#define MASK_TOCNT		    0xF


#define bST_CMD_HI          0x10000
#define bST_DAT0_HI         0x20000
#define MASK_BLOCK_NUM	    0x0FFFF


#define bSIF_SDIO_INT       0x200
#define bSIF_FIFO_OF        0x100
#define bSIF_BLOCK_GAP      0x080
#define bSIF_TRANS_SC       0x040
#define bSIF_TRANS_ER       0x020
#define bSIF_DATA_TMO       0x010
#define bSIF_CMD_DONE       0x008
#define bSIF_RE_IDX_ER      0x004
#define bSIF_RE_CRC_WR      0x002
#define bSIF_RE_TMOUT       0x001


#define bSIE_SDIO_INT       0x200
#define bSIE_FIFO_OF        0x100
#define bSIE_BLOCK_GAP      0x080
#define bSIE_TRANS_SC       0x040
#define bSIE_TRANS_ER       0x020
#define bSIE_DATA_TMO       0x010
#define bSIE_CMD_DONE       0x008
#define bSIE_RE_IDX_ER      0x004
#define bSIE_RE_CRC_WR      0x002
#define bSIE_RE_TMOUT       0x001


#define BLOCK_SIZE		    0xFFF0000
#define BLOCK_NUM		    0x000FFFF


#define bTM_EMMC_BOOT	    0x04
#define bTM_GAP_STOP	    0x02
#define bTM_WR_SD		    0x01

#ifdef __cplusplus
}
#endif

#endif


#ifndef __CH568ECDCSFR_H__
#define __CH568ECDCSFR_H__

#ifdef __cplusplus
extern "C" {
#endif


#define		AES_SM4_BASE_ADDR			(0x0040c400)

#define		R32_AES_SM4_CTRL		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x00)))
   #define   bKEYE_ACT_IE      0x00010000
   #define   MASK_Key_LEN      0x00000C00
   #define   bBCIPHER_MOD      0x00000200
   #define   bALGRM_MOD        0x00000100
   #define   MASK_ED_CLK_PRE   0x00000030
   #define   bEDMOD_SELT       0x00000008
   #define   bRDDAT_ED_EN      0x00000004
   #define   bWRDAT_ED_EN      0x00000002
   #define   bKEYE_EN          0x00000001

#define		R32_AES_SM4_INT_FG		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x04)))
   #define   bKEYE_ACT_IF      0x00010000


#define		R32_AES_SM4_KEY7		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x08)))
#define		R32_AES_SM4_KEY6		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x0c)))
#define		R32_AES_SM4_KEY5		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x10)))
#define		R32_AES_SM4_KEY4		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x14)))
#define		R32_AES_SM4_KEY3		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x18)))
#define		R32_AES_SM4_KEY2		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x1c)))
#define		R32_AES_SM4_KEY1		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x20)))
#define		R32_AES_SM4_KEY0		(*((PUINT32V)(AES_SM4_BASE_ADDR + 0x24)))


#define		R32_AES_SM4_IV3		    (*((PUINT32V)(AES_SM4_BASE_ADDR + 0x28)))
#define		R32_AES_SM4_IV2		    (*((PUINT32V)(AES_SM4_BASE_ADDR + 0x2c)))
#define		R32_AES_SM4_IV1		    (*((PUINT32V)(AES_SM4_BASE_ADDR + 0x30)))
#define		R32_AES_SM4_IV0		    (*((PUINT32V)(AES_SM4_BASE_ADDR + 0x34)))

#ifdef __cplusplus
}

#endif

#endif


#ifndef __SDIO_TYPE__
#define __SDIO_TYPE__

#ifdef __cplusplus
extern "C" {
#endif


#define R2    							0x01
#define R1    							0x02
#define R1B   							0x03


#define CMD0 							0
#define CMD0_R 							R1


#define CMD1 							1
#define CMD1_R 							R1


#define CMD8 							8
#define CMD8_R 							R3


#define CMD9 							9
#define CMD9_R 							R1


#define CMD10 							10
#define CMD10_R 						R1


#define CMD12 							12
#define CMD12_R 						R1B


#define CMD13 							13
#define CMD13_R 						R2


#define CMD16 							16
#define CMD16_R 						R1


#define CMD17 							17
#define CMD17_R 						R1


#define CMD18 							18
#define CMD18_R 						R1


#define CMD24 							24
#define CMD24_R 						R1


#define CMD25 							25
#define CMD25_R 						R1


#define CMD27 							27
#define CMD27_R 						R1


#define CMD28 							28
#define CMD28_R 						R1B

#define CMD29 							29
#define CMD29_R 						R1B

#define CMD30 							30
#define CMD30_R 						R1


#define CMD32 							32
#define CMD32_R 						R1


#define CMD33 							33
#define CMD33_R 						R1


#define CMD35 							35
#define CMD35_R 						R1


#define CMD36 							36
#define CMD36_R 						R1


#define CMD38 							38
#define CMD38_R 						R1B


#define CMD42 							42
#define CMD42_R							R1B


#define CMD55 							55
#define CMD55_R 						R1


#define CMD56 							56
#define CMD56_R 						R1


#define CMD58 							58
#define CMD58_R 						R3


#define CMD59 							59
#define CMD59_R 						R1


#define ACMD13 							13
#define ACMD13_R 						R2


#define ACMD22 							22
#define ACMD22_R 						R1


#define ACMD23 							23
#define ACMD23_R 						R1


#define ACMD41 							41
#define ACMD41_R 						R1


#define ACMD42 							42
#define ACMD42_R 						R1


#define ACMD51 							51
#define ACMD51_R 						R1


#define SD_NO_ERR			     		0x00
#define SD_ERR_NO_CARD		 			0x60
#define SD_ERR_USER_PARAM      			0x61
#define SD_ERR_CARD_PARAM		 		0x62
#define	SD_ERR_VOL_NOTSUSP        		0x63
#define SD_ERR_OVER_CARDRANGE			0x64
#define SD_ERR_UNKNOWN_CARD       		0x65
#define SD_ERR_WP_PROTECT         		0x66
#define SD_CARD_BUSY              		0x67
#define SD_BLOCK_ERROR            		0x68


#define SD_ERR_CMD_RESPTYPE	 			0x69
#define SD_ERR_CMD_TIMEOUT     			0x6A
#define SD_ERR_CMD_RESP		 			0x6B
#define SD_Power_Up_Busy          		0x6C


#define SD_ERR_DATA_CRC16      			0x6D
#define SD_ERR_DATA_START_TOK			0x6E
#define	SD_ERR_DATA_RESP		 		0x6F


#define SD_ERR_TIMEOUT_WAIT    			0x70
#define SD_ERR_TIMEOUT_READ    			0x71
#define	SD_ERR_TIMEOUT_WRITE	 		0x72
#define SD_ERR_TIMEOUT_ERASE   			0x73
#define	SD_ERR_TIMEOUT_WAITIDLE 		0x74


#define	SD_ERR_WRITE_BLK				0x75
#define	SD_ERR_WRITE_BLKNUMS      		0x76
#define SD_ERR_WRITE_PROTECT			0x77


#define SD_ERR_CREATE_SEMSD				0xA0


#define	CARDTYPE_SD						0x00
#define CARDTYPE_MMC					0x01
#define SD_UCOSII_SMALLWAIT				0xFF
#define SD_READREG_TIMEOUT				0x08


#define MSK_OCR_33			 			0xC0


#define SD_IDLE_WAIT_MAX     			10000


#define SD_CMD_TIMEOUT   	 			0x0FFFF


#define READ_TIMEOUT_100MS      		100 * SD_CLOCK / 4194304

#define WRITE_TIMEOUT_250MS				250 * SD_CLOCK / 4194304


#define TAAC_POS 						1
#define NSAC_POS						2
#define READ_BL_LEN_POS					5
#define C_SIZE_POS1						6
#define C_SIZE_POS2						7
#define C_SIZE_POS3						8
#define C_SIZE_MULT_POS1				9
#define C_SIZE_MULT_POS2				10
#define SECTOR_SIZE_POS1				10
#define SECTOR_SIZE_POS2				11
#define R2WFACTOR_POS 					12


#define ERASE_GRP_SIZE_POS   			10
#define ERASE_GRP_MULTI_POS1 			10
#define ERASE_GRP_MULTI_POS2 			11


#define TAAC_MSK						0x07
#define NSAC_MSK						0x78
#define READ_BL_LEN_MSK				 	0x0F
#define C_SIZE_MSK1						0x03
#define C_SIZE_MSK3						0xC0
#define C_SIZE_MULT_MSK1 				0x03
#define C_SIZE_MULT_MSK2 				0x80
#define R2WFACTOR_MSK					0x1C
#define SECTOR_SIZE_MSK1				0x3F
#define SECTOR_SIZE_MSK2				0x80
#define ERASE_GRP_SIZE_MSK 				0x7C
#define ERASE_GRP_MULTI_MSK1 			0x03
#define ERASE_GRP_MULTI_MSK2 			0xE0
#define SD_BLOCK_LEN       				512


#ifdef __cplusplus
}
#endif

#endif


